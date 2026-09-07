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

    def test_meta_demo_hints_follow_dev_jwt(self):
        response = self.client.get("/api/meta")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("demoHints", response.json())
        self.assertTrue(response.json()["demoHints"])

    def test_draft_publish_autosyncs_default_not_custom(self):
        first_prompt = "看拼音写字：chāo（默认课" + self.marker + "）"
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", first_prompt, "超")},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        first_id = imported.json()["items"][0]["id"]
        first = self.client.post("/api/drafts/" + str(first_id) + "/publish", headers=self.admin)
        self.assertEqual(first.status_code, 200, first.text)
        first_point = first.json()["id"]

        custom = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-pending-" + self.marker,
                "note": "L4 易错字",
                "kinds": ["zi"],
                "levels": ["L4"],
                "grades": ["三年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(custom.status_code, 200, custom.text)
        custom_id = custom.json()["id"]
        before_count = custom.json()["itemCount"]
        self.assertGreaterEqual(before_count, 1)

        extra_prompt = "看拼音写字：yuè（待同步" + self.marker + "）"
        extra = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", extra_prompt, "月")},
            headers=self.admin,
        )
        extra_draft = extra.json()["items"][0]["id"]
        published = self.client.post("/api/drafts/" + str(extra_draft) + "/publish", headers=self.admin)
        self.assertEqual(published.status_code, 200, published.text)
        point_id = published.json()["id"]
        self.assertNotEqual(point_id, first_point)

        courses = self.client.get("/api/courses", headers=self.kid)
        self.assertEqual(courses.status_code, 200, courses.text)
        payload = courses.json()
        default = next((row for row in payload if row.get("name") == "默认课程"), None)
        if default is None:
            created = self.client.post(
                "/api/courses",
                json={"name": "默认课程", "note": "系统预置", "kinds": [], "levels": [], "grades": []},
                headers=self.kid,
            )
            self.assertEqual(created.status_code, 200, created.text)
            courses = self.client.get("/api/courses", headers=self.kid)
            payload = courses.json()
            default = next((row for row in payload if row.get("name") == "默认课程"), None)
        custom_row = next((row for row in payload if row.get("id") == custom_id), None)
        self.assertIsNotNone(default)
        self.assertIsNotNone(custom_row)
        self.assertEqual(default["itemCount"], default["publishedCount"])
        self.assertEqual(default.get("pendingCount"), 0)

        default_today = self.client.get("/api/courses/" + str(default["id"]) + "/today", headers=self.kid)
        self.assertEqual(default_today.status_code, 200, default_today.text)
        self.assertGreater(default_today.json().get("itemCount") or 0, 0)

        with connect() as conn:
            attached = conn.execute(
                "SELECT 1 FROM course_items WHERE course_id = %s AND point_id = %s",
                (default["id"], point_id),
            ).fetchone()
            custom_has = conn.execute(
                "SELECT 1 FROM course_items WHERE course_id = %s AND point_id = %s",
                (custom_id, point_id),
            ).fetchone()
        self.assertIsNotNone(attached)
        self.assertIsNone(custom_has)
        self.assertGreaterEqual(custom_row.get("pendingCount") or 0, 1)
        self.assertEqual(custom_row["itemCount"], before_count)

        synced = self.client.post("/api/courses/" + str(custom_id) + "/sync", headers=self.kid)
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertGreaterEqual(synced.json()["added"], 1)
        self.assertEqual(synced.json().get("pendingCount"), 0)

    def test_unauthorized(self):
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 401)

    def test_student_library_matches_default_course(self):
        with connect() as conn:
            published = conn.execute("SELECT COUNT(*) AS n FROM knowledge_published").fetchone()["n"]
        self.assertGreater(published, 0)

        catalog = self.client.get("/api/library?limit=100&offset=0&answers=1", headers=self.kid)
        self.assertEqual(catalog.status_code, 200, catalog.text)
        visible = catalog.json()["total"]
        self.assertGreater(visible, 0)
        self.assertLessEqual(visible, published)
        self.assertTrue(catalog.json()["items"])
        self.assertTrue(all(item.get("answer") for item in catalog.json()["items"]))

        empty_param = self.client.get("/api/library?resourceId=&answers=1", headers=self.kid)
        self.assertEqual(empty_param.status_code, 200, empty_param.text)
        self.assertEqual(empty_param.json()["total"], visible)

        unlinked = self.client.get("/api/library?resourceId=0&answers=1", headers=self.kid)
        self.assertEqual(unlinked.status_code, 200, unlinked.text)
        named = self.client.get("/api/library?resourceId=unlinked&answers=1", headers=self.kid)
        self.assertEqual(named.status_code, 200, named.text)
        self.assertEqual(named.json()["total"], unlinked.json()["total"])

        extra = self.client.post(
            "/api/courses",
            json={"name": "接口课-cov-" + self.marker, "note": "", "kinds": [], "levels": [], "grades": []},
            headers=self.kid,
        )
        self.assertEqual(extra.status_code, 200, extra.text)
        self.assertEqual(extra.json()["itemCount"], visible)
        self.assertEqual(extra.json().get("pendingCount"), 0)

        courses = self.client.get("/api/courses", headers=self.kid)
        default = next((row for row in courses.json() if row.get("name") == "默认课程"), None)
        if default is None:
            created = self.client.post(
                "/api/courses",
                json={"name": "默认课程", "note": "系统预置", "kinds": [], "levels": [], "grades": []},
                headers=self.kid,
            )
            self.assertEqual(created.status_code, 200, created.text)
            default = created.json()
        self.assertGreater(default["itemCount"], 0)
        self.assertEqual(default.get("publishedCount"), visible)
        self.assertTrue(default.get("isDefault"))

        synced = self.client.post("/api/courses/" + str(default["id"]) + "/sync", headers=self.kid)
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertGreaterEqual(synced.json()["itemCount"], visible)

        coverage = self.client.get("/api/library/coverage", headers=self.kid)
        self.assertEqual(coverage.status_code, 200, coverage.text)
        self.assertEqual(coverage.json()["total"], published)
        self.assertIn("entryCount", coverage.json())
        self.assertIn("studiedEntries", coverage.json())
        self.assertIn("byEntryGrade", coverage.json())
        self.assertGreaterEqual(coverage.json()["entryCount"], 1)
        self.assertLessEqual(coverage.json()["entryCount"], coverage.json()["total"])
        self.assertGreaterEqual(coverage.json()["inCourse"], visible)
        self.assertEqual(sum(row["total"] for row in coverage.json()["byKind"]), published)
        self.assertEqual(sum(row["total"] for row in coverage.json()["byGrade"]), published)

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
        self.assertIn("entryCount", payload)
        self.assertTrue(payload["total"] >= 1)
        self.assertGreaterEqual(payload["entryCount"], 1)
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

        today = self.client.get("/api/courses/" + str(course_id) + "/today", headers=self.kid)
        self.assertEqual(today.status_code, 200, today.text)
        today_item = next(item for item in today.json()["items"] if item["id"] == point_id)
        self.assertEqual(today_item.get("questionType"), "dictation")
        self.assertEqual(today.json().get("mode"), "learn")
        self.assertEqual(today.json().get("defaultMode"), "learn")

        recite_today = self.client.get(
            "/api/courses/" + str(course_id) + "/today?mode=recite",
            headers=self.kid,
        )
        self.assertEqual(recite_today.status_code, 200, recite_today.text)
        self.assertFalse(recite_today.json().get("energyCharged"))
        self.assertEqual(recite_today.json().get("newEnergy"), 0)
        recited = next(item for item in recite_today.json()["items"] if item["id"] == point_id)
        self.assertEqual(recited.get("answer"), "测")

        recite = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "测", "mode": "recite"},
            headers=self.kid,
        )
        self.assertEqual(recite.status_code, 200, recite.text)
        self.assertTrue(recite.json()["correct"])
        self.assertFalse(recite.json()["updateSm2"])
        self.assertTrue(recite.json()["isNew"])

        peek = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "", "reveal": True, "mode": "learn"},
            headers=self.kid,
        )
        self.assertEqual(peek.status_code, 200, peek.text)
        self.assertEqual(peek.json()["quality"], 3)
        self.assertFalse(peek.json()["correct"])
        self.assertTrue(peek.json()["updateSm2"])
        self.assertEqual(peek.json()["state"]["n"], 1)
        self.assertEqual(peek.json()["state"]["lapses"], 0)

        blocked = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "", "reveal": True, "mode": "test"},
            headers=self.kid,
        )
        self.assertEqual(blocked.status_code, 400, blocked.text)

        review = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "测", "mode": "test"},
            headers=self.kid,
        )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["quality"], 5)
        self.assertTrue(review.json()["correct"])
        self.assertTrue(review.json()["updateSm2"])

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

    def test_review_pref_and_today_summary_fields(self):
        prompt = "看拼音写字：huì（摘要" + self.marker + "）"
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", prompt, "会")},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        draft_id = imported.json()["items"][0]["id"]
        published = self.client.post("/api/drafts/" + str(draft_id) + "/publish", headers=self.admin)
        self.assertEqual(published.status_code, 200, published.text)
        point_id = published.json()["id"]

        course = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-摘要-" + self.marker,
                "note": "进度摘要",
                "kinds": ["zi"],
                "levels": ["L4"],
                "grades": ["三年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(course.status_code, 200, course.text)
        course_id = course.json()["id"]
        self.assertFalse(course.json().get("reviewDefaultTest"))

        today = self.client.get("/api/courses/" + str(course_id) + "/today", headers=self.kid)
        self.assertEqual(today.status_code, 200, today.text)
        payload = today.json()
        self.assertIn("progress", payload)
        self.assertIn(payload["progress"].get("status"), ("remaining", "idle", "done", "empty"))
        self.assertFalse(payload.get("reviewDefaultTest"))
        self.assertTrue(any(item["id"] == point_id for item in payload["items"]))

        patched = self.client.patch(
            "/api/courses/" + str(course_id),
            json={"reviewDefaultTest": True},
            headers=self.kid,
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertTrue(patched.json().get("reviewDefaultTest"))
        self.assertIn("progress", patched.json())

        listed = self.client.get("/api/courses", headers=self.kid)
        row = next((item for item in listed.json() if item.get("id") == course_id), None)
        self.assertIsNotNone(row)
        self.assertTrue(row.get("reviewDefaultTest"))
        self.assertIn("progress", row)
        self.assertTrue(row["progress"].get("title"))

        peek = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "", "reveal": True, "mode": "learn"},
            headers=self.kid,
        )
        self.assertEqual(peek.status_code, 200, peek.text)
        self.assertEqual(peek.json()["quality"], 3)
        self.assertIn("feedback", peek.json())
        self.assertIn("模糊", peek.json()["feedback"].get("hint") or "")

        wrong = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "绘", "mode": "test"},
            headers=self.kid,
        )
        self.assertEqual(wrong.status_code, 200, wrong.text)
        self.assertFalse(wrong.json()["correct"])
        self.assertTrue(wrong.json()["feedback"].get("wrongChars"))
        self.assertIn("记下", wrong.json()["feedback"].get("title") or "")

        stats = self.client.get("/api/courses/" + str(course_id) + "/stats", headers=self.kid)
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertGreaterEqual(stats.json()["today"]["todayPracticed"], 1)
        self.assertIsNotNone(stats.json()["today"]["todayAccuracy"])
        self.assertIn("items", stats.json())
        self.assertIn("mastery", stats.json())
        self.assertGreaterEqual(stats.json()["mastery"]["total"], 1)
        self.assertTrue(stats.json().get("summary"))
        self.assertTrue(stats.json().get("reviewDefaultTest"))

        today_after = self.client.get("/api/courses/" + str(course_id) + "/today", headers=self.kid)
        self.assertTrue(today_after.json().get("reviewDefaultTest"))
        self.assertGreaterEqual(today_after.json()["progress"]["todayPracticed"], 1)

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
            "elementary-idioms",
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
        self.assertGreaterEqual(synced.json()["ok"], 40)
        self.assertGreaterEqual(
            synced.json()["inserted"] + synced.json()["updated"] + synced.json().get("unchanged", 0),
            40,
        )

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
        self.assertEqual(incremental.json()["packs"], 13)
        self.assertEqual(incremental.json()["skipped"], 13)

        rebuilt = self.client.post("/api/resources/sync-all", headers=self.admin)
        self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
        self.assertEqual(rebuilt.json()["packs"], 13)
        self.assertEqual(rebuilt.json()["synced"], 13)

        idioms = slugs.get("elementary-idioms") or {}
        if not idioms:
            listed = self.client.get("/api/resources", headers=self.admin)
            slugs = {row["slug"]: row for row in listed.json()}
            idioms = slugs["elementary-idioms"]
        self.assertEqual(idioms.get("title"), "小学成语")
        self.assertGreaterEqual(idioms.get("pointCount") or 0, 1900)

    def test_unpublished_draft_hidden_from_library(self):
        prompt = "看拼音写字：cáng（待审隐藏" + self.marker + "）"
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", prompt, "藏")},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        draft_id = imported.json()["items"][0]["id"]

        hidden = self.client.get("/api/library?kind=zi&level=L4&answers=1&limit=500", headers=self.admin)
        self.assertEqual(hidden.status_code, 200, hidden.text)
        self.assertFalse(any(item.get("prompt") == prompt for item in hidden.json()["items"]))

        published = self.client.post("/api/drafts/" + str(draft_id) + "/publish", headers=self.admin)
        self.assertEqual(published.status_code, 200, published.text)
        point_id = published.json()["id"]

        shown = self.client.get("/api/library?kind=zi&level=L4&answers=1&limit=500", headers=self.admin)
        self.assertTrue(any(item.get("id") == point_id for item in shown.json()["items"]))

        again = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", prompt, "藏")},
            headers=self.admin,
        )
        self.assertEqual(again.status_code, 200, again.text)
        pending_id = again.json()["items"][0]["id"]
        blocked = self.client.get("/api/library?kind=zi&level=L4&answers=1&limit=500", headers=self.admin)
        self.assertFalse(any(item.get("id") == point_id for item in blocked.json()["items"]))

        discarded = self.client.patch(
            "/api/drafts/" + str(pending_id),
            json={"status": "discarded"},
            headers=self.admin,
        )
        self.assertEqual(discarded.status_code, 200, discarded.text)
        restored = self.client.get("/api/library?kind=zi&level=L4&answers=1&limit=500", headers=self.admin)
        self.assertTrue(any(item.get("id") == point_id for item in restored.json()["items"]))

    def test_draft_pagination_and_batch_publish(self):
        rows = "".join(
            csv_row("zi", "L4", "看拼音写字：pī（批量" + self.marker + str(index) + "）", "批")
            for index in range(3)
        )
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + rows},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        ids = [item["id"] for item in imported.json()["items"]]
        self.assertEqual(len(ids), 3)

        page = self.client.get("/api/drafts?status=draft&limit=2&offset=0", headers=self.admin)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertGreaterEqual(page.json()["total"], 3)
        self.assertEqual(page.json()["limit"], 2)
        self.assertLessEqual(len(page.json()["items"]), 2)

        empty = self.client.post("/api/drafts/publish-batch", json={"ids": []}, headers=self.admin)
        self.assertEqual(empty.status_code, 400, empty.text)

        batch = self.client.post(
            "/api/drafts/publish-batch",
            json={"ids": ids[:2]},
            headers=self.admin,
        )
        self.assertEqual(batch.status_code, 200, batch.text)
        self.assertEqual(batch.json()["ok"], 2)
        self.assertEqual(batch.json()["fail"], 0)

        leftover = self.client.get("/api/drafts?status=draft&limit=200", headers=self.admin)
        leftover_ids = {item["id"] for item in leftover.json()["items"]}
        self.assertNotIn(ids[0], leftover_ids)
        self.assertNotIn(ids[1], leftover_ids)
        self.assertIn(ids[2], leftover_ids)

        library = self.client.get("/api/library?kind=zi&level=L4&answers=1&limit=500", headers=self.admin)
        published_ids = {item["id"] for item in library.json()["items"]}
        self.assertTrue({item["id"] for item in batch.json()["items"]}.issubset(published_ids))
        leftover_prompt = "看拼音写字：pī（批量" + self.marker + "2）"
        self.assertFalse(any(item.get("prompt") == leftover_prompt for item in library.json()["items"]))

    def test_multi_card_entry_audience_and_question_type(self):
        import json

        lemma = "接口成语"
        key = "api-" + self.marker
        pack = {
            "points": [
                {
                    "key": key,
                    "kind": "idiom",
                    "level": "L4",
                    "grade": "一年级上",
                    "prompt": "形容接口练习（四字）",
                    "answer": lemma,
                    "tags": "成语;测试",
                    "source": "接口测试",
                    "lemma": lemma,
                    "question_type": "recite",
                    "audience": "all",
                },
                {
                    "key": key + ":char_judge",
                    "kind": "idiom",
                    "level": "L4",
                    "grade": "一年级上",
                    "prompt": "下面的写法对不对？",
                    "answer": "对",
                    "tags": "成语;测试",
                    "source": "接口测试",
                    "lemma": lemma,
                    "question_type": "char_judge",
                    "audience": "lower",
                    "options": {"display": lemma},
                },
                {
                    "key": key + ":meaning_choice",
                    "kind": "idiom",
                    "level": "L4",
                    "grade": "一年级上",
                    "prompt": "「接口成语」的意思是？",
                    "answer": "形容接口练习",
                    "tags": "成语;测试",
                    "source": "接口测试",
                    "lemma": lemma,
                    "question_type": "meaning_choice",
                    "audience": "upper",
                    "options": {
                        "choices": ["形容接口练习", "景色很美丽", "做事很认真", "形容心情不好"]
                    },
                },
            ]
        }
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": json.dumps(pack, ensure_ascii=False)},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["ok"], 3)
        draft_ids = [item["id"] for item in imported.json()["items"]]
        published_ids = []
        for draft_id in draft_ids:
            published = self.client.post("/api/drafts/" + str(draft_id) + "/publish", headers=self.admin)
            self.assertEqual(published.status_code, 200, published.text)
            published_ids.append(published.json()["id"])

        catalog = self.client.get(
            "/api/library?kind=idiom&level=L4&grade=" + "一年级上" + "&answers=1&limit=500",
            headers=self.admin,
        )
        self.assertEqual(catalog.status_code, 200, catalog.text)
        ours = [
            item
            for item in catalog.json()["items"]
            if item.get("id") in published_ids or item.get("lemma") == lemma
        ]
        self.assertEqual(len(ours), 3)
        self.assertEqual({item.get("questionType") for item in ours}, {"recite", "char_judge", "meaning_choice"})
        self.assertEqual(len({item.get("entryKey") for item in ours}), 1)

        lower = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-低-" + self.marker,
                "note": "一年级受众",
                "kinds": ["idiom"],
                "levels": ["L4"],
                "grades": ["一年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(lower.status_code, 200, lower.text)
        lower_id = lower.json()["id"]
        today = self.client.get("/api/courses/" + str(lower_id) + "/today?mode=learn", headers=self.kid)
        self.assertEqual(today.status_code, 200, today.text)
        types = {item.get("questionType") for item in today.json()["items"] if item.get("id") in published_ids}
        self.assertEqual(types, {"recite", "char_judge"})
        recite = next(item for item in today.json()["items"] if item.get("id") in published_ids and item.get("questionType") == "recite")
        self.assertTrue(recite.get("answer") or recite.get("lemma"))

        mixed = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-混-" + self.marker,
                "note": "低高年级都勾",
                "kinds": ["idiom"],
                "levels": ["L4"],
                "grades": ["一年级上", "五年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(mixed.status_code, 200, mixed.text)
        mixed_today = self.client.get(
            "/api/courses/" + str(mixed.json()["id"]) + "/today?mode=learn",
            headers=self.kid,
        )
        self.assertEqual(mixed_today.status_code, 200, mixed_today.text)
        mixed_types = {
            item.get("questionType")
            for item in mixed_today.json()["items"]
            if item.get("id") in published_ids
        }
        self.assertEqual(mixed_types, {"recite", "char_judge", "meaning_choice"})

    def test_entry_grades_span_courses_without_duplicate_cards(self):
        import json

        glyphs = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳"
        lemma = "跨" + "".join(glyphs[int(ch, 16)] for ch in self.marker[:3])
        pack = {
            "points": [
                {
                    "key": "cross-a-" + self.marker,
                    "kind": "idiom",
                    "level": "L4",
                    "grade": "一年级上",
                    "prompt": "一年级也有" + self.marker + "（四字）",
                    "answer": lemma,
                    "tags": "成语;测试",
                    "source": "接口测试",
                    "lemma": lemma,
                    "question_type": "recite",
                    "audience": "all",
                },
                {
                    "key": "cross-b-" + self.marker,
                    "kind": "idiom",
                    "level": "L4",
                    "grade": "二年级上",
                    "prompt": "二年级也有" + self.marker + "（四字）",
                    "answer": lemma,
                    "tags": "成语;测试",
                    "source": "接口测试",
                    "lemma": lemma,
                    "question_type": "recite",
                    "audience": "all",
                },
            ]
        }
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": json.dumps(pack, ensure_ascii=False)},
            headers=self.admin,
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["ok"], 2)
        published_ids = []
        for item in imported.json()["items"]:
            published = self.client.post("/api/drafts/" + str(item["id"]) + "/publish", headers=self.admin)
            self.assertEqual(published.status_code, 200, published.text)
            published_ids.append(published.json()["id"])

        with connect() as conn:
            entry = conn.execute(
                "SELECT grades, levels FROM knowledge_entry WHERE entry_key = %s",
                ("idiom:" + lemma,),
            ).fetchone()
            grades = {
                row["grade"]
                for row in conn.execute(
                    "SELECT grade FROM knowledge_entry_grade WHERE entry_key = %s",
                    ("idiom:" + lemma,),
                ).fetchall()
            }
        self.assertIsNotNone(entry)
        self.assertIn("一年级上", entry["grades"])
        self.assertIn("二年级上", entry["grades"])
        self.assertEqual(grades, {"一年级上", "二年级上"})

        booklet = self.client.get(
            "/api/library?kind=idiom&level=L4&grade=" + "二年级上" + "&answers=1&limit=500",
            headers=self.admin,
        )
        self.assertEqual(booklet.status_code, 200, booklet.text)
        booklet_ours = [item for item in booklet.json()["items"] if item.get("lemma") == lemma]
        self.assertEqual(len(booklet_ours), 1)
        self.assertEqual(booklet_ours[0]["grade"], "二年级上")

        preview = self.client.get(
            "/api/library?kind=idiom&level=L4&grades=" + "二年级上" + "&answers=1&limit=500",
            headers=self.admin,
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        preview_ours = [item for item in preview.json()["items"] if item.get("lemma") == lemma]
        self.assertEqual(len(preview_ours), 1)
        self.assertIn("二年级上", preview_ours[0].get("entryGrades") or "")
        self.assertIn("一年级上", preview_ours[0].get("entryGrades") or "")

        grade1 = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-跨1-" + self.marker,
                "note": "一年级再学",
                "kinds": ["idiom"],
                "levels": ["L4"],
                "grades": ["一年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(grade1.status_code, 200, grade1.text)
        stats1 = self.client.get("/api/courses/" + str(grade1.json()["id"]) + "/stats", headers=self.kid)
        self.assertEqual(stats1.status_code, 200, stats1.text)
        ours1 = [item for item in stats1.json()["items"] if item.get("id") in published_ids]
        self.assertEqual(len(ours1), 1)
        self.assertIn("一年级也有", ours1[0].get("prompt") or "")

        grade2 = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-跨2-" + self.marker,
                "note": "二年级再学",
                "kinds": ["idiom"],
                "levels": ["L4"],
                "grades": ["二年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(grade2.status_code, 200, grade2.text)
        stats2 = self.client.get("/api/courses/" + str(grade2.json()["id"]) + "/stats", headers=self.kid)
        self.assertEqual(stats2.status_code, 200, stats2.text)
        ours2 = [item for item in stats2.json()["items"] if item.get("id") in published_ids]
        self.assertEqual(len(ours2), 1)
        self.assertIn("二年级也有", ours2[0].get("prompt") or "")
        self.assertNotEqual(ours1[0]["id"], ours2[0]["id"])
        self.assertIn("passCount", ours1[0])

    def test_parent_seed_authz_wrong_book_week_and_wizard(self):
        parent = self._login("parent", "parent123")
        me = self.client.get("/api/me", headers=parent)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["role"], "parent")
        self.assertTrue(me.json().get("students"))
        kid_id = next(item["id"] for item in me.json()["students"] if item["name"] == "kid")

        family = self.client.get("/api/family", headers=parent)
        self.assertEqual(family.status_code, 200, family.text)
        names = [item["name"] for item in family.json()["students"]]
        self.assertIn("kid", names)
        self.assertTrue(family.json()["students"][0].get("week"))
        self.assertTrue(family.json()["students"][0].get("today"))

        blocked = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\nzi,L4,三年级上,看拼音写字：jiā,家,测试,接口测试\n"},
            headers=parent,
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        upload = self.client.post(
            "/api/resources",
            data={"scope": "user"},
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers=parent,
        )
        self.assertEqual(upload.status_code, 403)

        stranger = self.client.post(
            "/api/register",
            json={"name": "otherkid-" + self.marker, "password": "kid1234", "role": "user"},
        )
        self.assertEqual(stranger.status_code, 200, stranger.text)
        other_headers = {"Authorization": "Bearer " + stranger.json()["token"]}
        other_id = stranger.json()["user"]["id"]

        prompt = "看拼音写字：cuò（家长" + self.marker + "）"
        imported = self.client.post(
            "/api/drafts/import",
            json={"text": "kind,level,grade,prompt,answer,tags,source\n" + csv_row("zi", "L4", prompt, "错")},
            headers=self.admin,
        )
        draft_id = imported.json()["items"][0]["id"]
        published = self.client.post("/api/drafts/" + str(draft_id) + "/publish", headers=self.admin)
        point_id = published.json()["id"]
        course = self.client.post(
            "/api/courses",
            json={
                "name": "接口课-家长-" + self.marker,
                "note": "错题再练",
                "kinds": ["zi"],
                "levels": ["L4"],
                "grades": ["三年级上"],
            },
            headers=self.kid,
        )
        self.assertEqual(course.status_code, 200, course.text)
        course_id = course.json()["id"]
        other_course = self.client.post(
            "/api/courses",
            json={"name": "接口课-他人-" + self.marker, "note": "", "kinds": ["zi"], "levels": ["L4"], "grades": ["三年级上"]},
            headers=other_headers,
        )
        self.assertEqual(other_course.status_code, 200, other_course.text)
        hidden = self.client.get("/api/courses/" + str(other_course.json()["id"]) + "/stats", headers=parent)
        self.assertEqual(hidden.status_code, 403, hidden.text)
        listed = self.client.get("/api/courses?studentId=" + str(other_id), headers=parent)
        self.assertEqual(listed.status_code, 403, listed.text)
        wrong = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "措", "mode": "test"},
            headers=self.kid,
        )
        self.assertEqual(wrong.status_code, 200, wrong.text)
        self.assertFalse(wrong.json()["correct"])

        parent_review = self.client.post(
            "/api/courses/" + str(course_id) + "/review",
            json={"pointId": point_id, "answer": "错", "mode": "test"},
            headers=parent,
        )
        self.assertEqual(parent_review.status_code, 403, parent_review.text)
        parent_today = self.client.get("/api/courses/" + str(course_id) + "/today", headers=parent)
        self.assertEqual(parent_today.status_code, 403, parent_today.text)

        wrong_book = self.client.get("/api/courses/" + str(course_id) + "/wrong-book", headers=parent)
        self.assertEqual(wrong_book.status_code, 200, wrong_book.text)
        self.assertTrue(any(item["id"] == point_id for item in wrong_book.json()["items"]))
        self.assertFalse(wrong_book.json()["canDrill"])

        kid_book = self.client.get("/api/courses/" + str(course_id) + "/wrong-book", headers=self.kid)
        self.assertTrue(kid_book.json()["canDrill"])
        replay = self.client.get(
            "/api/courses/" + str(course_id) + "/today?wrongBook=1",
            headers=self.kid,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json().get("wrongBook"))
        self.assertEqual(replay.json().get("mode"), "test")
        self.assertTrue(any(item["id"] == point_id for item in replay.json()["items"]))

        week = self.client.get("/api/courses/" + str(course_id) + "/week", headers=parent)
        self.assertEqual(week.status_code, 200, week.text)
        self.assertGreaterEqual(week.json()["daysPracticed"], 1)
        self.assertTrue(week.json()["summary"])

        pref = self.client.patch(
            "/api/courses/" + str(course_id),
            json={"reviewDefaultTest": True, "dailyMinutesCap": 15},
            headers=parent,
        )
        self.assertEqual(pref.status_code, 200, pref.text)
        self.assertTrue(pref.json()["reviewDefaultTest"])
        self.assertEqual(pref.json()["dailyMinutesCap"], 15)

        wizard = self.client.get("/api/wizard?grade=三年级上", headers=parent)
        self.assertEqual(wizard.status_code, 200, wizard.text)
        self.assertEqual(wizard.json()["plan"]["grade"], "三年级上")
        created = self.client.post(
            "/api/courses",
            json={
                "wizard": True,
                "studentId": kid_id,
                "grades": ["三年级上"],
                "name": "接口课-向导-" + self.marker,
            },
            headers=parent,
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertGreater(created.json()["itemCount"], 0)
        self.assertEqual(created.json()["studentId"], kid_id)
        self.assertIn("三年级上", created.json()["grades"])


if __name__ == "__main__":
    unittest.main()
