#!/usr/bin/env python3
"""Bounded record/evidence checks. A passing result never certifies readiness."""
from __future__ import annotations

import argparse
import codecs
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

__version__ = '0.1.1'
LIMIT = 4 * 1024 * 1024
LABELS = ('Verified', 'Unverified', 'Assumptions')
QUALIFIERS = ('[UNSUPPORTED CLAIM]', '[ASSUMPTION]', '[LIKELY ISSUE]', '[SAFETY/COMPLIANCE]')
SHA = re.compile(r'[a-f0-9]{64}\Z')
BLOCK = re.compile(r'(?m)^\s*Verified:[^\n]*\n\s*Unverified:[^\n]*\n\s*Assumptions:[^\n]*')


class InputError(ValueError):
    pass


def result(scope, findings=None, error=None):
    return {'schema_version': 1, 'tool_version': __version__, 'scope': scope,
            'status': 'error' if error else ('findings' if findings else 'pass'),
            'readiness': 'not_assessed', 'findings': findings or [], 'error': error}


def finding(code, where, detail):
    return {'code': code, 'where': str(where), 'detail': detail}


def read_text(path):
    path = Path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise InputError('Text input must be a regular file')
    if info.st_size > LIMIT:
        raise InputError('Text input exceeds the documented 4 MiB limit')
    with path.open('rb') as file:
        opened = os.fstat(file.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise InputError('Opened text input must be a regular file')
        raw = file.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise InputError('Text input grew beyond the documented limit')
    encoding = 'utf-16' if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else 'utf-8-sig'
    text = raw.decode(encoding)
    if '\x00' in text:
        raise InputError('NUL input: use UTF-8 or BOM-marked UTF-16')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def record_errors(text):
    lines = text.rstrip().splitlines()
    if len(lines) < 3:
        return ['Missing terminal three-line verification record']
    fields = []
    for label, line in zip(LABELS, lines[-3:]):
        m = re.fullmatch(re.escape(label) + r':[ \t]*(.*)', line)
        if not m:
            return ['Record must be terminal, consecutive, unadorned Verified/Unverified/Assumptions lines']
        value = m.group(1).strip()
        if not value or re.match(r'^(?:<[^>]*>|\.\.\.|TBD\b|TODO\b|N/?A\s*$|\[(?:insert|fill|todo|tbd)\b)', value, re.I):
            fields.append('%s is empty or a template placeholder' % label)
        if value in QUALIFIERS:
            fields.append('%s has a qualification label without any detail' % label)
    # Only classify fences for the record itself, not arbitrary delivery claims.
    opened = None
    for i, line in enumerate(lines):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if marker:
            fence, rest = marker.groups()
            if opened is None:
                opened = (fence[0], len(fence))
            elif fence[0] == opened[0] and len(fence) >= opened[1] and not rest.strip():
                opened = None
        if i >= len(lines) - 3 and opened is not None:
            fields.append('A quoted code example is not the delivery record')
            break
    return fields


class VisibleText(HTMLParser):
    """Simple HTML text extraction, not browser/rendered-document verification."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'div', 'br', 'li', 'tr', 'td', 'h1', 'h2', 'h3', 'pre'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
        if tag in ('p', 'div', 'li', 'tr', 'td', 'h1', 'h2', 'h3', 'pre'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def lint(args):
    scope = 'record-structure-and-placement'
    if args.response.suffix.lower() not in ('.md', '.markdown', '.txt'):
        raise InputError('Response must be plain text or Markdown')
    text = read_text(args.response)
    errors = record_errors(text)
    if args.tier in (1, 2) and not any(re.match(r'^(Verified|Unverified|Assumptions):', x) for x in text.splitlines()):
        errors = []
    out = [finding('record', args.response, e) for e in errors]
    for path in args.artefact:
        if path.suffix.lower() not in ('.md', '.markdown', '.txt', '.html', '.htm'):
            raise InputError('Unsupported artefact format; export text or HTML explicitly')
        body = read_text(path)
        if path.suffix.lower() in ('.html', '.htm'):
            parser = VisibleText()
            parser.feed(body)
            body = ''.join(parser.parts)
        body = re.sub(r'\n[ \t]*\n', '\n', body)
        if BLOCK.search(body):
            out.append(finding('footer-placement', path, 'Internal verification record appears in a client artefact'))
    return (1 if out else 0), result(scope, out)


def fingerprint(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise InputError('Artefact must be a regular non-symlink file: %s' % path)
    digest = hashlib.sha256()
    with path.open('rb') as f:
        first = os.fstat(f.fileno())
        for part in iter(lambda: f.read(65536), b''):
            digest.update(part)
        last = os.fstat(f.fileno())
    if (first.st_size, first.st_mtime_ns, first.st_ino) != (last.st_size, last.st_mtime_ns, last.st_ino):
        raise InputError('Artefact changed while hashing')
    return {'sha256': digest.hexdigest(), 'bytes': last.st_size}


def approved_paths(paths):
    if not paths:
        raise InputError('Supply every final artefact explicitly')
    for p in paths:
        if p.is_symlink():
            raise InputError('Symlink artefacts are not supported')
    resolved = [str(p.resolve(strict=True)) for p in paths]
    if len(set(resolved)) != len(resolved):
        raise InputError('Duplicate artefact path')
    return resolved


def hash_stream(f):
    f.seek(0)
    digest = hashlib.sha256()
    size = 0
    for part in iter(lambda: f.read(65536), b''):
        size += len(part)
        digest.update(part)
    return digest.hexdigest(), size


def stop_child(p):
    """Best-effort owned group/tree termination while the direct child is alive."""
    if p.poll() is not None:
        return
    if os.name == 'nt':
        tool = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
        subprocess.run([str(tool), '/PID', str(p.pid), '/T', '/F'], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # the owned group already exited
    if p.poll() is None:
        p.kill()
    p.wait(timeout=5)


def run_check(args):
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.max_output_bytes <= 0:
        raise InputError('Timeout and output limit must be positive finite values')
    command = args.command
    if command and command[0] == '--':
        command = command[1:]
    if not command:
        raise InputError('Supply an explicitly approved command after --')
    paths = approved_paths(args.artefact)
    before = {p: fingerprint(p) for p in paths}
    # Exclusive creation checks destination permissions/existence BEFORE execution.
    fd = os.open(str(args.receipt), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    record = {'schema_version': 1, 'tool_version': __version__, 'run_id': uuid.uuid4().hex,
              'command_sha256': hashlib.sha256(json.dumps(command, ensure_ascii=True).encode('ascii')).hexdigest(),
              'complete': False, 'returncode': None, 'status': 'error', 'artifacts': [],
              'completion_scope': 'direct_child', 'descendant_completion': 'not_assessed',
              'started_at': time.time()}
    error = None
    p = None
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            start = time.monotonic()
            try:
                creationflags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
                p = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     creationflags=creationflags, start_new_session=os.name != 'nt')
                while p.poll() is None:
                    if time.monotonic() - start >= args.timeout:
                        record['status'] = 'timeout'
                        stop_child(p)
                        break
                    if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > args.max_output_bytes:
                        record['status'] = 'output_limit'
                        stop_child(p)
                        break
                    time.sleep(0.02)
                p.wait(timeout=5)
                record['returncode'] = p.returncode
                if record['status'] not in ('timeout', 'output_limit'):
                    record['status'] = 'success' if p.returncode == 0 else 'failed'
                    record['complete'] = True
            except (OSError, subprocess.SubprocessError) as exc:
                error = type(exc).__name__ + ': execution did not complete'
                record['status'] = 'error'
            finally:
                if p is not None and p.poll() is None:
                    stop_child(p)
            record['stdout_sha256'], record['stdout_bytes'] = hash_stream(out)
            record['stderr_sha256'], record['stderr_bytes'] = hash_stream(err)
            if record['stdout_bytes'] + record['stderr_bytes'] > args.max_output_bytes:
                record.update(status='output_limit', complete=False)
        for path in paths:
            after = fingerprint(path)
            record['artifacts'].append({'path': path, 'before': before[path], 'after': after})
        if record['complete'] and any(x['before'] != x['after'] for x in record['artifacts']):
            record['status'] = 'artifact_changed'
    except (OSError, ValueError) as exc:
        error = type(exc).__name__ + ': artefact or receipt processing failed'
        record.update(status='error', complete=False)
    finally:
        record['finished_at'] = time.time()
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=True, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
    rc = 0 if record['status'] == 'success' else (1 if record['status'] in ('failed', 'artifact_changed') else 2)
    obj = result('execution-record', [] if rc == 0 else [finding(record['status'], args.receipt, 'Check did not establish successful unchanged-artefact evidence')], error=error if rc == 2 else None)
    if rc == 2:
        obj['status'] = 'error'
    obj['receipt'] = str(args.receipt)
    obj['completion_scope'] = 'direct_child'
    obj['descendant_completion'] = 'not_assessed'
    return rc, obj


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise InputError('Duplicate JSON key')
        obj[key] = value
    return obj


def verify(args):
    paths = approved_paths(args.artefact)
    current = {p: fingerprint(p) for p in paths}
    out = []
    for source in args.receipt:
        try:
            r = json.loads(read_text(source), object_pairs_hook=unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(InputError('Non-finite JSON number')))
        except RecursionError:
            raise InputError('Receipt JSON nesting exceeds parser support') from None
        required = ('schema_version', 'tool_version', 'run_id', 'command_sha256', 'complete', 'returncode', 'status',
                    'artifacts', 'stdout_sha256', 'stderr_sha256', 'stdout_bytes', 'stderr_bytes',
                    'completion_scope', 'descendant_completion')
        if not isinstance(r, dict) or any(k not in r for k in required):
            raise InputError('Receipt has missing required fields')
        if type(r['schema_version']) is not int or r['schema_version'] != 1 or r['tool_version'] != __version__:
            raise InputError('Unsupported receipt schema/producer version')
        if r['completion_scope'] != 'direct_child' or r['descendant_completion'] != 'not_assessed':
            raise InputError('Unsupported receipt completion scope')
        if not isinstance(r['run_id'], str) or not re.fullmatch(r'[a-f0-9]{32}', r['run_id']):
            raise InputError('Invalid receipt run ID')
        if not isinstance(r['status'], str) or r['status'] not in ('success', 'failed', 'artifact_changed', 'timeout', 'output_limit', 'error'):
            raise InputError('Invalid receipt status')
        if type(r['complete']) is not bool or (r['returncode'] is not None and type(r['returncode']) is not int):
            raise InputError('Invalid completion/returncode types')
        for key in ('command_sha256', 'stdout_sha256', 'stderr_sha256'):
            if not isinstance(r[key], str) or not SHA.fullmatch(r[key]):
                raise InputError('Invalid receipt digest')
        for key in ('stdout_bytes', 'stderr_bytes'):
            if type(r[key]) is not int or r[key] < 0:
                raise InputError('Invalid output byte count')
        rows = r['artifacts']
        if not isinstance(rows, list) or any(not isinstance(x, dict) or set(x) != {'path', 'before', 'after'} for x in rows):
            raise InputError('Invalid artefact manifest')
        if len(rows) != len(paths) or {x['path'] for x in rows} != set(paths):
            raise InputError('Receipt paths differ from explicitly approved artefacts')
        for row in rows:
            for key in ('before', 'after'):
                value = row[key]
                if not isinstance(value, dict) or set(value) != {'sha256', 'bytes'} or not isinstance(value['sha256'], str) or not SHA.fullmatch(value['sha256']) or type(value['bytes']) is not int or value['bytes'] < 0:
                    raise InputError('Invalid artefact fingerprint')
            if row['before'] != row['after'] or row['after'] != current[row['path']]:
                out.append(finding('stale-artifact', source, 'Receipt does not bind the current unchanged bytes'))
        if r['complete'] is not True or r['returncode'] != 0 or r['status'] != 'success':
            out.append(finding('unsuccessful-check', source, 'Required receipt is not a completed successful check'))
    return (1 if out else 0), result('receipt-and-artifact-binding', out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    lp = sub.add_parser('lint', help='Check record structure/placement, never semantic readiness')
    lp.add_argument('--response', type=Path, required=True)
    lp.add_argument('--artefact', type=Path, action='append', default=[])
    lp.add_argument('--tier', type=int, choices=(1, 2, 3), default=3)
    rp = sub.add_parser('run', help='Execute an explicitly approved check and record bounded evidence')
    rp.add_argument('--receipt', type=Path, required=True)
    rp.add_argument('--artefact', type=Path, action='append', required=True)
    rp.add_argument('--timeout', type=float, default=60)
    rp.add_argument('--max-output-bytes', type=int, default=1024 * 1024)
    rp.add_argument('command', nargs=argparse.REMAINDER)
    vp = sub.add_parser('verify', help='Compare explicit receipts with explicit final artefacts')
    vp.add_argument('--receipt', type=Path, action='append', required=True)
    vp.add_argument('--artefact', type=Path, action='append', required=True)
    args = parser.parse_args()
    try:
        rc, obj = {'lint': lint, 'run': run_check, 'verify': verify}[args.action](args)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        rc, obj = 2, result(args.action, error=type(exc).__name__ + ': ' + str(exc))
    print(json.dumps(obj, ensure_ascii=True, sort_keys=True))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
