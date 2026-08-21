.PHONY: setup doctor test openmontage-update intake render qa
setup:
	./scripts/setup.sh
doctor:
	python3 scripts/doctor.py
test:
	python3 -m unittest discover -s tests -v
openmontage-update:
	./scripts/openmontage.sh update
intake:
	@test -n "$(URL)" || (echo 'Usage: make intake URL=https://…' >&2; exit 2)
	python3 scripts/new_story.py "$(URL)"
render:
	@test -n "$(STORY)" || (echo 'Usage: make render STORY=work/story.json' >&2; exit 2)
	python3 scripts/render_reference.py "$(STORY)" "$(or $(VIDEO),dist/news.mp4)"
qa:
	@test -n "$(VIDEO)" || (echo 'Usage: make qa VIDEO=dist/news.mp4' >&2; exit 2)
	python3 scripts/check_video.py "$(VIDEO)"
