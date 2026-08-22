import importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("daily", ROOT / "scripts/daily_story.py")
daily = importlib.util.module_from_spec(spec); spec.loader.exec_module(daily)
result_spec = importlib.util.spec_from_file_location("result", ROOT / "scripts/write_automation_result.py")
result = importlib.util.module_from_spec(result_spec); result_spec.loader.exec_module(result)
def valid(): return json.loads((ROOT / "tests/fixtures/daily-story-valid.json").read_text())
class DailyStoryTest(unittest.TestCase):
 def test_valid_payload_and_structure(self):
  story=daily.build_story(daily.validate(valid()))
  self.assertEqual([x["end"] for x in story["script"]],[3,6,9,12,14]); self.assertNotIn("AI", "".join(x["narration"] for x in story["script"][:-1]))
 def test_invalid_json(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/"bad"; src.write_text("{"); run=subprocess.run([sys.executable,ROOT/"scripts/daily_story.py","prepare",src,Path(d)/"out"]); self.assertNotEqual(run.returncode,0)
 def test_required_and_security_validation(self):
  for mutate in (lambda p:p.pop("source_url"),lambda p:p.update(source_url="http://openai.com/x"),lambda p:p.pop("headline"),lambda p:p.update(points=["one"]),lambda p:p.update(request_id="../../bad")):
   payload=valid(); mutate(payload)
   with self.assertRaises(ValueError): daily.validate(payload)
 def test_caption_under_limit_unchanged(self): self.assertEqual(daily.caption("短い完全な見出し"), "短い完全な見出し")
 def test_caption_safely_wraps_without_rewriting(self):
  text="ChatGPT、13〜17歳向けに新しい体験を提供"
  wrapped=daily.caption(text); self.assertEqual(wrapped.replace("\n", ""), text); self.assertEqual(len(wrapped.splitlines()),2); self.assertTrue(all(len(x)<=18 for x in wrapped.splitlines()))
 def test_caption_without_safe_boundary_fails(self):
  with self.assertRaisesRegex(ValueError,"shorter caption upstream"): daily.caption("これは安全な区切りを一切持たない非常に長いニュース見出しです")
 def test_caption_never_ends_in_incomplete_phrase(self):
  wrapped=daily.caption("ChatGPT、13〜17歳向けに新しい体験を提供")
  self.assertFalse(wrapped.splitlines()[0].endswith("向けに"))
  with self.assertRaisesRegex(ValueError, "complete shorter caption upstream"):
   daily.caption("13〜17歳向けに")
 def test_hash_binds_filename_and_image_directory(self):
  payload=valid(); same=daily.build_story(dict(payload)); changed=dict(payload); changed["points"]=["内容を変更しました。",payload["points"][1]]; other=daily.build_story(changed)
  self.assertEqual(daily.filename(payload),daily.filename(dict(payload))); self.assertIn(same["content_hash"],same["image_asset_dir"])
  self.assertNotEqual(daily.filename(payload),daily.filename(changed)); self.assertNotEqual(same["image_asset_dir"],other["image_asset_dir"])
 def test_prompts_are_scene_specific(self):
  generator=(ROOT/"scripts/generate_story_images.py").read_text(); self.assertIn('story["image_scenes"]',generator); self.assertNotIn('" / ".join(claims)',generator)
 def test_image_budget_and_cache(self):
  story=daily.build_story(valid()); self.assertEqual(len(story["image_assets"]),4)
  generator=(ROOT/"scripts/generate_story_images.py").read_text(); self.assertIn("destination.is_file()",generator); self.assertIn("if len(prompts) > 4",generator); self.assertIn("no retry",generator)
 def test_generated_image_readiness_is_strict(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); payload=valid(); story=daily.build_story(payload); image_dir=root/story["request_id"]/story["content_hash"]/"daily-editorial-v1"; story["image_asset_dir"]=str(image_dir); image_dir.mkdir(parents=True)
   video=root/"video.mp4"; video.write_bytes(b"video")
   for name in story["image_assets"]: (image_dir/name).write_bytes(b"png")
   log={"status":"complete","content_hash":story["content_hash"],"expected_images":story["image_assets"],"images":[{"file":n,"result":"generated"} for n in story["image_assets"]]}; (image_dir/"image-generation-log.json").write_text(json.dumps(log))
   render={"used_generated_images":True,"content_hash":story["content_hash"],"image_directory":str(image_dir),"images":[str(image_dir/n) for n in story["image_assets"]]}; video.with_suffix(".render.json").write_text(json.dumps(render))
   self.assertTrue(result.generated_images_ready(story,video)); (image_dir/story["image_assets"][0]).write_bytes(b""); self.assertFalse(result.generated_images_ready(story,video))
 def test_fallback_is_not_publish_ready(self):
  source=(ROOT/"scripts/write_automation_result.py").read_text(); self.assertIn('"auto_publish_ready": success and used',source)
 def test_regression_targets_remain(self):
  workflow=(ROOT/".github/workflows/render-video.yml").read_text(); self.assertTrue(all(x in workflow for x in ("teen_chatgpt","generic_url","daily_story")))
if __name__ == "__main__": unittest.main()
