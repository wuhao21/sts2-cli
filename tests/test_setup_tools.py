"""Checks for update data integrity and honest batch completion reporting."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import io
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('version', [2, 3])
def test_extract_localization_validates_checksum(tmp_path, version):
    extract = load_module('extract_localization', ROOT / 'scripts/extract_localization.py').extract
    data = b'{"STRIKE.title": "Strike"}'
    name = b'localization/eng/cards.json\0'
    entry = (struct.pack('<I', len(name)) + name + struct.pack('<QQ', 0, len(data))
             + hashlib.md5(data).digest() + struct.pack('<I', 0))
    directory = struct.pack('<I', 1) + entry
    header_size = 104 if version == 3 else 96
    base = header_size + len(directory)
    header = struct.pack('<6IQ', 0x43504447, version, 4, 5, 1, 2, base)
    if version == 3:
        header += struct.pack('<Q', header_size)
    pck = tmp_path / 'game.pck'
    pck.write_bytes(header + bytes(64) + directory + data)
    output = tmp_path / 'output'
    assert extract(pck, output) == 1
    target = output / 'localization_eng/cards.json'
    assert target.read_bytes() == data
    pck.write_bytes(pck.read_bytes()[:-1] + b'!')
    with pytest.raises(ValueError, match='checksum'):
        extract(pck, output)
    assert target.read_bytes() == data


@pytest.mark.parametrize('result, expected', [
    ({'completed': True, 'victory': False}, 0),
    ({'completed': True, 'victory': True}, 0),
    ({'error': 'EOF'}, 1),
    ({'error': 'stuck'}, 1),
    ({'timeout': True}, 1),
])
def test_batch_exit_requires_game_over(monkeypatch, result, expected):
    monkeypatch.syspath_prepend(str(ROOT / 'python'))
    runner = load_module('play_full_run', ROOT / 'python/play_full_run.py')
    monkeypatch.setattr(runner, 'play_run', lambda *args, **kwargs: result)
    monkeypatch.setattr(sys, 'argv', ['play_full_run.py', '1', 'Ironclad'])
    assert runner.main() == expected


def test_batch_timeout_stops_without_retrying_or_counting_completion(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'python'))
    runner = load_module('play_full_run_timeout', ROOT / 'python/play_full_run.py')
    responses = [
        {'type': 'ready'},
        {'type': 'decision', 'decision': 'combat_play', 'round': 2,
         'player': {'hp': 57}, 'hand': [], 'energy': 0, 'enemies': [{'hp': 72}]},
        {'type': 'error', 'error_code': 'combat_turn_timeout', 'message': 'Turn stalled',
         'player': {'hp': 52}},
    ]
    sent = io.StringIO()

    class Process:
        stdin = sent
        stdout = io.StringIO(''.join(json.dumps(r) + '\n' for r in responses))

        def terminate(self):
            pass

        def wait(self, **kwargs):
            pass

    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *args, **kwargs: Process())
    result = runner.play_run('timeout', verbose=False, log=False)
    assert not result.get('completed')
    assert result['error'] == 'Turn stalled'
    commands = [json.loads(line) for line in sent.getvalue().splitlines()]
    assert [cmd.get('action', cmd['cmd']) for cmd in commands] == ['start_run', 'end_turn', 'quit']
