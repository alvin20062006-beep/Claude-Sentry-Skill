"""Build a complete Claude Sentry Skill ZIP or a standalone Claude Skill ZIP."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path, skill: bool = False) -> int:
    source = ROOT / 'skills/claude-sentry-skill' if skill else ROOT
    prefix = 'claude-sentry-skill' if skill else 'Claude-Sentry-Skill'
    allowed_dirs = {'.claude-plugin', 'hooks', 'skills', 'tests', 'tools'}
    allowed_root = {'README.md', 'LICENSE', '.gitignore'}
    entries = []
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if path.is_symlink() or not path.is_file() or '__pycache__' in relative.parts:
            continue
        if path.suffix in ('.pyc', '.zip'):
            continue
        if not skill and relative.parts[0] not in allowed_dirs and str(relative) not in allowed_root:
            continue
        entries.append((path, f'{prefix}/{relative.as_posix()}'))
    if skill:
        entries.append((ROOT / 'LICENSE', f'{prefix}/LICENSE'))
    output = output.resolve()
    if output.is_relative_to(source.resolve()):
        raise ValueError('Choose an output path outside the source folder')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as z:
        checksums = []
        for path, name in entries:
            data = path.read_bytes()
            info = zipfile.ZipInfo(name, (2026, 11, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == '.sh' else 0o100644) << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
            checksums.append(hashlib.sha256(data).hexdigest() + '  ' + name[len(prefix) + 1:])
        z.writestr(f'{prefix}/SHA256SUMS.txt', '\n'.join(checksums) + '\n')
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP integrity check failed')
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--full', type=Path, help='Output path for the complete project ZIP')
    mode.add_argument('--skill', type=Path, help='Output path for a standalone Skill ZIP')
    args = parser.parse_args()
    output = args.skill or args.full
    count = build(output, skill=args.skill is not None)
    print(f'{output.resolve()} ({count} source files + SHA256SUMS.txt)')
