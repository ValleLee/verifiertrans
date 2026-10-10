from pathlib import Path

from verifier_trans.pipeline.artifacts import copy_tree


def test_copy_tree_resolves_directory_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text("{}\n", encoding="utf-8")

    real_target = tmp_path / "classified" / "current"
    real_target.mkdir(parents=True)
    compat = tmp_path / "compat" / "verifier"
    compat.parent.mkdir()
    compat.symlink_to(real_target)

    copy_tree(source, compat)

    assert compat.is_symlink()
    assert compat.resolve() == real_target
    assert (real_target / "manifest.json").read_text(encoding="utf-8") == "{}\n"
