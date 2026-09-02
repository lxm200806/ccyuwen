"""登录、发布、今日队列、复习与课程维护。需要可用的 PostgreSQL。"""
import uuid
import unittest

from fastapi.testclient import TestClient

from app.db import connect
from app.main import app


def csv_row(kind, level, prompt, answer, grade="三年级上"):
    return f"{kind},{level},{grade},{prompt},{answer},测试,接口测试\n"


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()
        cls.marker = uuid.uuid4().hex[:8]
        cls.admin = cls._login("admin", "admin123")
        cls.kid = cls._login("kid", "kid123")

    @classmethod
    def tearDownClass(cls):
        try:
            cls._cleanup_fixture_data()
        finally:
            cls._ctx.__exit__(None, None, None)

    @classmethod
    def _cleanup_fixture_data(cls):
        with connect() as conn:
            conn.execute(
                """
                DELETE FROM review_log
                WHERE point_id IN (SELECT id FROM knowledge_published WHERE source = %s)
                   OR course_id IN (SELECT id FROM courses WHERE name LIKE %s OR name LIKE %s)
                """,
                ("接口测试", "接口课-%", "已改名-%"),
            )
            conn.execute(
                """
                DELETE FROM review_state
                WHERE point_id IN (SELECT id FROM knowledge_published WHERE source = %s)
                   OR course_id IN (SELECT id FROM courses WHERE name LIKE %s OR name LIKE %s)
                """,
                ("接口测试", "接口课-%", "已改名-%"),
            )
            conn.execute(
                """
                DELETE FROM course_items
                WHERE point_id IN (SELECT id FROM knowledge_published WHERE source = %s)
                """,
                ("接口测试",),
            )
            conn.execute("DELETE FROM knowledge_published WHERE source = %s", ("接口测试",))
            conn.execute("DELETE FROM knowledge_draft WHERE source = %s", ("接口测试",))
            conn.execute(
                "DELETE FROM courses WHERE name LIKE %s OR name LIKE %s",
                ("接口课-%", "已改名-%"),
            )
            conn.commit()

    @classmethod
    def _login(cls, name, password):
        response = cls.client.post("/api/login", json={"name": name, "password": password})
        if response.status_code != 200:
            raise unittest.SkipTest("数据库不可用或默认账号未就绪: " + response.text)
        return {"Authorization": "Bearer " + response.json()["token"]}

    def test_login_rejected(self):
        response = self.client.post("/api/login", json={"name": "admin", "password": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_unauthorized(self):
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 401)

    def test_kid_cannot_upload(self):
        response = self.client.post(
            "/api/resources",
            data={"scope": "user"},
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers=self.kid,
        )
        self.assertEqual(response.status_code, 403)

    def test_publish_today_review_and_course_lifecycle(self):
        prompt = "看拼音写字：cè（接口" + self.marker + "）"
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", prompt, "测")},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["ok"], 1)
        draft_id = imported.json()["items"][0]["id"]

        published = self.client.post("/api/drafts/" + str(draft_id) + "/publish", headers=self.admin)
        self.assertEqual(published.status_code, 200, published.text)
        point_id = published.json()["id"]

        library = self.client.get("/api/library?kind=zi&level=L4", headers=self.kid)
        self.assertEqual(library.status_code, 200, library.text)
        payload = library.json()
        self.assertIn("items", payload)
        self.assertTrue(payload["total"] >= 1)
        self.assertTrue(all("answer" not in item for item in payload["items"]))

        catalog = self.client.get("/api/library?kind=zi&level=L4&answers=1", headers=self.kid)
        self.assertEqual(catalog.status_code, 200, catalog.text)
        shown = [item for item in catalog.json()["items"] if item.get("id") == point_id]
        self.assertTrue(shown)
        self.assertEqual(shown[0].get("answer"), "测")

        packs = self.client.get("/api/resources", headers=self.kid)
        self.assertEqual(packs.status_code, 200, packs.text)
        self.assertTrue(any(item.get("isPack") for item in packs.json()))
        self.assertTrue(all("path" not in item for item in packs.json()))

        course = self.client.post(
            "/api/courses",
            json={"name": "接口课-" + self.marker, "note": "L4 易错字", "kinds": ["zi"], "levels": ["L4"], "grades": ["三年级上"]},
            headers=self.kid,
        )
        self.assertEqual(course.status_code, 200, course.text)
        course_id = course.json()["id"]
        self.assertGreaterEqual(course.json()["itemCount"], 1)
        self.assertEqual(course.json().get("newEnergy"), 30)
        self.assertTrue(course.json().get("plan", {}).get("dayCount") >= 1)

        today = self.client.get("/api/courses/" + str(course_id) + "/today", headers=self.kid)
        self.assertEqual(today.status_code, 200, today.text)
        self.assertTrue(any(item["id"] == point_id for item in today.json()["items"]))

        review = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "测"},
            headers=self.kid,
        )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["quality"], 5)
        self.assertTrue(review.json()["correct"])

        extra_prompt = "看拼音写字：shì（同步" + self.marker + "）"
        extra = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", extra_prompt, "试")},
            headers=self.admin,
        )
        extra_id = extra.json()["items"][0]["id"]
        self.client.post("/api/drafts/" + str(extra_id) + "/publish", headers=self.admin)
        synced = self.client.post("/api/courses/" + str(course_id) + "/sync", headers=self.kid)
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertGreaterEqual(synced.json()["added"], 1)

        renamed = self.client.patch(
            "/api/courses/" + str(course_id),
            json={"name": "已改名-" + self.marker},
            headers=self.kid,
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "已改名-" + self.marker)

        deleted = self.client.delete("/api/courses/" + str(course_id), headers=self.kid)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        missing = self.client.get("/api/courses/" + str(course_id) + "/today", headers=self.kid)
        self.assertEqual(missing.status_code, 404)

    def test_grade3_original_backup_and_sync(self):
        listed = self.client.get("/api/resources", headers=self.admin)
        self.assertEqual(listed.status_code, 200, listed.text)
        slugs = {row["slug"]: row for row in listed.json()}
        for slug in (
            "grade1-shang",
            "grade1-xia",
            "grade2-shang",
            "grade2-xia",
            "grade3-shang",
            "grade3-xia",
            "grade4-shang",
            "grade4-xia",
            "grade5-shang",
            "grade5-xia",
            "grade6-shang",
            "grade6-xia",
        ):
            self.assertIn(slug, slugs, slug)
            self.assertIn(slug + "-original", slugs, slug)

        pack = slugs["grade3-shang"]
        self.assertGreaterEqual(pack.get("version") or 0, 1)
        self.assertEqual(pack.get("syncState"), "synced")
        for slug, row in slugs.items():
            if row.get("isPack"):
                self.assertEqual(row.get("syncState"), "synced", slug)
                self.assertEqual(row.get("version"), row.get("syncedVersion"), slug)

        original = self.client.get("/api/resources/" + str(slugs["grade1-shang-original"]["id"]), headers=self.admin)
        self.assertEqual(original.status_code, 200, original.text)
        self.assertIn("咏鹅", original.json()["original"])

        json_id = slugs["grade3-shang"]["id"]
        detail = self.client.get("/api/resources/" + str(json_id), headers=self.admin)
        self.assertGreaterEqual(detail.json()["linkedPoints"], 40)

        filtered = self.client.get("/api/library?resourceId=" + str(json_id) + "&limit=200", headers=self.admin)
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertGreaterEqual(filtered.json()["total"], 40)
        self.assertTrue(all(item.get("source_resource_id") == json_id for item in filtered.json()["items"]))
        self.assertIn("三年级上", filtered.json()["items"][0].get("resourceTitle") or "")

        unlinked = self.client.get("/api/library?resourceId=0&limit=200", headers=self.admin)
        self.assertEqual(unlinked.status_code, 200, unlinked.text)
        self.assertTrue(all(not item.get("source_resource_id") for item in unlinked.json()["items"]))

        synced = self.client.post("/api/resources/" + str(json_id) + "/sync", headers=self.admin)
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertEqual(synced.json()["ok"], 40)
        self.assertEqual(synced.json()["inserted"] + synced.json()["updated"], 40)

        grade1 = self.client.post("/api/resources/" + str(slugs["grade1-shang"]["id"]) + "/sync", headers=self.admin)
        self.assertEqual(grade1.status_code, 200, grade1.text)
        self.assertGreaterEqual(grade1.json()["ok"], 20)

        grade3x = self.client.post("/api/resources/" + str(slugs["grade3-xia"]["id"]) + "/sync", headers=self.admin)
        self.assertEqual(grade3x.status_code, 200, grade3x.text)
        self.assertGreaterEqual(grade3x.json()["ok"], 20)

        grade6 = self.client.post("/api/resources/" + str(slugs["grade6-xia"]["id"]) + "/sync", headers=self.admin)
        self.assertEqual(grade6.status_code, 200, grade6.text)
        self.assertGreaterEqual(grade6.json()["ok"], 15)

        incremental = self.client.post("/api/resources/sync-incremental", headers=self.admin)
        self.assertEqual(incremental.status_code, 200, incremental.text)
        self.assertEqual(incremental.json()["packs"], 12)
        self.assertEqual(incremental.json()["skipped"], 12)

        rebuilt = self.client.post("/api/resources/sync-all", headers=self.admin)
        self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
        self.assertEqual(rebuilt.json()["packs"], 12)
        self.assertEqual(rebuilt.json()["synced"], 12)


if __name__ == "__main__":
    unittest.main()
