from pathlib import Path

from omarum import screen


def test_editor_titles():
    assert screen.parse_editor("jetbrains-idea", "wazifa – CompanyService.java") == ("wazifa", "CompanyService.java")
    assert screen.parse_editor("jetbrains-pycharm", "omarum – omarum/brains.py") == ("omarum", "brains.py")
    assert screen.parse_editor("code", "● CompanyService.java - wazifa - Visual Studio Code") == ("wazifa", "CompanyService.java")
    assert screen.parse_editor("firefox", "GitHub – something") is None
    assert screen.parse_editor("jetbrains-idea", "Welcome to IntelliJ IDEA") is None


def test_project_dir_from_intellij_recent_projects(tmp_path):
    home = tmp_path
    proj = home / "Projects" / "wazifa"
    proj.mkdir(parents=True)
    opts = home / ".config/JetBrains/IntelliJIdea2026.3/options"
    opts.mkdir(parents=True)
    (opts / "recentProjects.xml").write_text('<entry key="$USER_HOME$/Projects/wazifa"><value frameTitle="wazifa – X.java"/></entry>')
    assert screen.project_dir("wazifa", home) == proj
    assert screen.project_dir("nope", home) is None


def test_find_file_skips_build_output(tmp_path):
    src = tmp_path / "server/src/main/java/org/oji/wazifa/company/service/impl"
    src.mkdir(parents=True)
    (src / "CompanyService.java").write_text("class CompanyService {}")
    built = tmp_path / "server/target/classes"
    built.mkdir(parents=True)
    (built / "CompanyService.java").write_text("copy")
    assert screen.find_file(tmp_path, "CompanyService.java") == src / "CompanyService.java"
    assert screen.find_file(tmp_path, "Missing.java") is None


def test_note_sends_code_only_when_it_changed(tmp_path):
    f = tmp_path / "server/src/CompanyService.java"
    f.parent.mkdir(parents=True)
    f.write_text("public class CompanyService {\n  // hi\n}\n")
    seen = screen.Seen()
    first = screen.note_for(f, tmp_path, "IntelliJ", seen)
    assert "server/src/CompanyService.java" in first and "public class CompanyService" in first
    again = screen.note_for(f, tmp_path, "IntelliJ", seen)
    assert "still" in again.lower() and "public class" not in again
    f.write_text("public class CompanyService { int changed; }\n")
    import os, time
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert "changed" in screen.note_for(f, tmp_path, "IntelliJ", seen)


def test_long_files_are_trimmed(tmp_path):
    f = tmp_path / "Big.java"
    f.write_text("".join(f"line {i}\n" for i in range(5000)))
    note = screen.note_for(f, tmp_path, "IntelliJ", screen.Seen())
    assert "line 0" in note and "line 4999" not in note and "trimmed" in note
