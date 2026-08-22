import importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("daily", ROOT/"scripts/daily_story.py"); daily=importlib.util.module_from_spec(spec); spec.loader.exec_module(daily)
def valid():
 return {"request_id":"2026-08-23-openai-example","news_key":"key","source_url":"https://openai.com/news/example","article_url":"https://aitoolwatch.jp/articles/example","headline":"新しいAI機能を発表","hook":"新機能が発表されました。","summary":"仕事の流れを短くできます。","points":["既存製品へ追加されます。","利用者が設定できます。"],"narration_terms":{"AI":"エーアイ"}}
class DailyStoryTest(unittest.TestCase):
 def test_valid_payload_and_structure(self):
  p=daily.validate(valid()); story=daily.build_story(p)
  self.assertEqual([x["end"] for x in story["script"]],[3,6,9,12,14]); self.assertNotIn("AI", "".join(x["narration"] for x in story["script"][:-1]))
 def test_invalid_json(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/"bad"; src.write_text("{"); r=subprocess.run([sys.executable,ROOT/"scripts/daily_story.py","prepare",src,Path(d)/"out"]); self.assertNotEqual(r.returncode,0)
 def test_required_and_security_validation(self):
  for mutate in (lambda p:p.pop("source_url"),lambda p:p.update(source_url="http://openai.com/x"),lambda p:p.pop("headline"),lambda p:p.update(points=["one"]),lambda p:p.update(request_id="../../bad")):
   p=valid(); mutate(p)
   with self.assertRaises(ValueError): daily.validate(p)
 def test_immutable_filename(self):
  p=valid(); self.assertEqual(daily.filename(p),daily.filename(dict(p)))
  changed=valid(); changed["summary"]+="変更"; self.assertNotEqual(daily.filename(p),daily.filename(changed)); self.assertTrue(daily.filename(p).startswith(p["request_id"]+"-"))
 def test_image_budget_cache_and_fallback_contract(self):
  story=daily.build_story(valid()); self.assertLessEqual(len(story["image_assets"]),4)
  generator=(ROOT/"scripts/generate_story_images.py").read_text(); self.assertIn('destination.is_file()',generator); self.assertIn('if len(prompts) > 4',generator); self.assertIn('no retry',generator)
 def test_publish_decision_requires_images(self):
  source=(ROOT/"scripts/write_automation_result.py").read_text(); self.assertIn('success and used',source); self.assertIn('"auto_publish_ready"',source)
 def test_regressions_are_still_workflow_targets(self):
  workflow=(ROOT/".github/workflows/render-video.yml").read_text(); self.assertIn("teen_chatgpt",workflow); self.assertIn("generic_url",workflow); self.assertIn("daily_story",workflow)
if __name__=="__main__": unittest.main()
