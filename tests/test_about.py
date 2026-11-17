from pathlib import Path


def test_index_has_about_section_with_every_project_link():
    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
    assert 'aria-labelledby="about-heading"' in html
    for href in [
        "https://github.com/serrebidev/equalizercast",
        "https://git.serrebiradio.com/serrebi/equalizercast",
        "https://projects.serrebiradio.com",
        "https://t.me/SerrebiProjects",
        "https://git.serrebiradio.com/serrebi/equalizercast/src/branch/main/CREDITS.md",
    ]:
        assert href in html, href
