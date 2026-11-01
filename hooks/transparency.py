#!/usr/bin/env python3
"""Claude Code local pre-ban notices: transparent, opt-in, no hidden moderation access."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import collections
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
REFERENCES = HERE.parent / 'skills' / 'claude-sentry-skill' / 'references'
RULES_FILE = REFERENCES / 'context_rules.json'
REGIONS_FILE = REFERENCES / 'supported_regions.json'

TOPIC_PATTERNS = {
    '网络安全政策主题': r'(?i)(?:勒索软件|恶意软件|木马|未授权入侵|窃取密码|钓鱼网站|ransomware|malware|credential theft|phishing)',
    '欺诈政策主题': r'(?i)(?:诈骗|伪造证件|恋爱诈骗|fraud|scam|fake identity)',
    '暴力与武器政策主题': r'(?i)(?:爆炸装置|制作炸弹|恐怖袭击|bioweapon|explosive device)',
}
REFUSAL = re.compile(r"(?i)(?:I (?:cannot|can't|won't) (?:help (?:you )?(?:with|to)|provide|assist with)|(?:抱歉|对不起).{0,20}(?:不能|无法).{0,12}(?:协助|提供|制作|执行|生成))")


def read_json(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def compiled_rules() -> tuple:
    rules = []
    for rule in read_json(RULES_FILE).get('rules', []):
        if not isinstance(rule, dict):
            continue
        try:
            rules.append((str(rule.get('title', '公开政策相关请求')),
                          tuple(re.compile(p, re.I) for p in rule.get('patterns', []))))
        except (re.error, TypeError):
            continue
    return tuple(rules)


def regex_hits(text: str) -> list[str]:
    """Read the *entire* text in bounded overlapping windows, not only its prefix."""
    if not isinstance(text, str):
        return []
    rules = compiled_rules()
    marks = []
    # O(ceil(n/12000) * rule_count); cap a single window, not the complete input.
    for at in range(0, len(text) or 1, 11000):
        sample = text[at: at + 12000]
        for name, patterns in rules:
            if name not in marks and any(p.search(sample) for p in patterns):
                marks.append(name)
        for title, pattern in TOPIC_PATTERNS.items():
            if re.search(pattern, sample) and title not in marks:
                marks.append(title)
        # Avoid unbounded effort for pathological pasted megabyte strings.
        if len(marks) >= 8:
            break
    return marks


def analyze(text: str) -> list[str]:
    return regex_hits(text)[:3]


def _message_text(entry: dict) -> str:
    """Only human-visible conversational text; never ingest tool results or file blobs."""
    if entry.get('type') not in ('user', 'assistant'):
        return ''
    message = entry.get('message')
    if not isinstance(message, dict):
        return ''
    content = message.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(x.get('text', '') for x in content
                         if isinstance(x, dict) and x.get('type') == 'text' and isinstance(x.get('text'), str))
    return ''


def transcript_context(path_str: str) -> dict:
    """Stream the complete local transcript; keep only recent turns and policy hints in RAM.

    No raw chat is written into state. A missing/malformed transcript is not a 'safe' finding.
    """
    if not isinstance(path_str, str) or not path_str:
        return {'available': False, 'recent': [], 'historical_marks': []}
    path = Path(path_str).expanduser()
    if not path.is_file():
        return {'available': False, 'missing': True, 'recent': [], 'historical_marks': []}
    recent = collections.deque(maxlen=16)
    historical = collections.deque(maxlen=12)
    incomplete = False
    deadline = time.monotonic() + 0.5
    try:
        with path.open(encoding='utf-8', errors='replace') as fd:
            for line in fd:
                if time.monotonic() >= deadline:
                    incomplete = True
                    break
                try:
                    entry = json.loads(line)
                    if not isinstance(entry, dict):
                        incomplete = True
                        continue
                    if entry.get('type') in ('user', 'assistant') and not isinstance(entry.get('message'), dict):
                        incomplete = True
                    content = _message_text(entry)
                    if not content: continue
                    role = entry['type']
                    # A turn may contain large text. Keep excerpts for context, but scan all text.
                    hit = regex_hits(content)
                    if hit:
                        historical.append({'role': role, 'marks': hit[:2], 'excerpt': content[:450]})
                    recent.append({'role': role, 'text': content[-4000:]})
                except (ValueError, KeyError, TypeError):
                    incomplete = True
                    continue
    except (OSError, UnicodeError):
        return {'available': False, 'recent': [], 'historical_marks': []}
    return {'available': True, 'incomplete': incomplete, 'recent': list(recent), 'historical_marks': list(historical)}


PACKAGING = re.compile(r'(?i)(小说|故事|剧本|角色扮演|扮演|虚构|假设|学术研究|模拟|翻译|编码|写成对话|fiction|novel|role.?play|hypothetical|pretend|translation|academic)')
INTENT_ACTION = re.compile(r'(?i)(怎么|如何|教我|写出|写一段|生成|给我|制作|实现|获取|绕过|骗取|诱骗|偷取|窃取|详细步骤|how to|write|build|generate|steal|bypass|step.by.step)')
SENSITIVE = re.compile(r'(?i)(钓鱼|诈骗|验证码|账号密码|木马|勒索软件|未授权|盗取|爆炸装置|危险武器|非法监控|phishing|fraud|scam|OTP|password|malware|ransomware|explosive)')


def contextual_marks(prompt: str, context: dict, prompt_hits=None) -> list[str]:
    """Correlate split requests; never claim to infer an unobservable hidden intent."""
    if not isinstance(prompt, str): return []
    turns = context.get('recent', [])
    previous_user = [t.get('text', '') for t in turns if t.get('role') == 'user'][-3:]
    prior = '\n'.join(previous_user)
    combined = (prior[-8000:] + '\n' + prompt) if prior else prompt
    if prompt_hits is None:
        prompt_hits = regex_hits(prompt)
    marks = []
    # e.g. novel in previous turn, actionable sensitive request in current turn;
    # or a harmful request split across two messages.
    if (SENSITIVE.search(combined) and INTENT_ACTION.search(combined)
            and (SENSITIVE.search(prompt) or INTENT_ACTION.search(prompt))):
        if PACKAGING.search(combined):
            marks.append('虚构、角色扮演或研究包装下的政策相关请求（需核对实际用途）')
        elif not prompt_hits and regex_hits(combined):
            marks.append('跨多轮组合后可能涉及公开政策的请求')
        elif SENSITIVE.search(prompt) and INTENT_ACTION.search(prompt) and not prompt_hits:
            marks.append('请求包含需结合上下文判断的敏感操作内容')
    if (context.get('historical_marks') and re.search(r'(?i)(继续|接着|沿用|接上|按照前面|按照上面|as above|continue)', prompt)
            and SENSITIVE.search(prompt) and not marks):
        marks.append('当前请求延续会话中曾出现的政策相关话题')
    return marks


NOTICE_PATTERNS = [
    # Recognize actual text that is visible, not invisible account actions.
    ('地区限制', re.compile(r'(?i)(unsupported (?:country|region|location)|supported countr(?:y|ies) policy|region (?:restriction|not supported)|不支持的地区|不支持地区|地区限制|所在地不受支持|所在国家.*不支持)')),
    ('账号限制', re.compile(r'(?i)(account (?:has been )?(?:suspended|disabled|restricted|locked)|account access (?:suspended|restricted)|账号(?:已被|受到|被)(?:暂停|停用|限制|锁定)|账户(?:已被|受到|被)(?:暂停|停用|限制|锁定))')),
    ('身份核验', re.compile(r'(?i)(identity verification required|verify your identity|verification (?:failed|required)|身份验(?:证|证失败)|身份核验|需要验证身份|实名核验)')),
    ('安全警告', re.compile(r'(?i)(usage policy violation|violation of (?:our |the )?usage policy|违反(?:了)?使用政策|违反(?:了)?服务条款|account warning|账号安全警告|账户安全警告)')),
]


def visible_notice(text: str) -> list[str]:
    if not isinstance(text, str): return []
    labels = []
    for label, pattern in NOTICE_PATTERNS:
        if pattern.search(text): labels.append(label)
    return labels


def _new_notice(label: str, text: str, session: str = '') -> bool:
    """Avoid repeating exact visible notices in adjacent events without storing text."""
    state = state_path()
    try:
        with state_lock(state):
            old = read_state(state)
            salt = old.get('salt') or secrets.token_hex(16)
            sig = hashlib.sha256((salt + ':' + session + ':' + label + ':' + text[:1200]).encode()).hexdigest()
            key = 'last_notice_digest_' + label
            if sig == old.get(key): return False
            old.update({'salt': salt, key: sig})
            save_state(state, old)
            return True
    except (OSError, TimeoutError):
        return True  # Still show the notice when deduplication storage is unavailable.


def timezone_name() -> str:
    if os.environ.get('TZ'):
        return os.environ['TZ'][:80]
    try:
        p = Path('/etc/localtime').resolve()
        txt = str(p)
        if '/zoneinfo/' in txt:
            return txt.split('/zoneinfo/', 1)[-1][:80]
    except OSError:
        pass
    import time
    return time.tzname[0] if time.tzname else 'unknown'


def get_egress() -> tuple[str | None, str | None, str]:
    """Read manual test inputs or opt-in third-party lookup; never send prompt text."""
    manual_ip = os.environ.get('CST_EGRESS_IP', '').strip()
    manual_cc = os.environ.get('CST_EGRESS_COUNTRY', '').strip().upper()
    if manual_ip:
        # An IP used only as a comparison identifier, not to prove region/location.
        try:
            manual_ip = str(ipaddress.ip_address(manual_ip))
        except ValueError:
            return None, None, 'invalid_input'
        return manual_ip, manual_cc if re.fullmatch(r'[A-Z]{2}', manual_cc) else None, 'manual'
    if os.environ.get('CST_REGION_LOOKUP') != '1':
        return None, None, 'disabled'
    try:
        req = urllib.request.Request('https://ipwho.is/', headers={'User-Agent': 'CST-Transparency/0.8'})
        with urllib.request.urlopen(req, timeout=1) as response:
            d = json.load(response)
        if not isinstance(d, dict) or d.get('success') is False:
            return None, None, 'failed'
        ip = str(d.get('ip', '')).strip()
        cc = str(d.get('country_code', '')).upper().strip()
        try:
            ip = str(ipaddress.ip_address(ip))
        except ValueError:
            return None, None, 'failed'
        return ip, cc if re.fullmatch(r'[A-Z]{2}', cc) else None, 'third_party'
    except (OSError, ValueError, TypeError, TimeoutError):
        return None, None, 'failed'


def state_path() -> Path:
    return Path(os.environ.get('CST_STATE_FILE', str(Path.home() / '.claude' / 'cst-local-state-v07.json')))


def read_state(path: Path) -> dict:
    return {k: v for k, v in read_json(path).items() if isinstance(v, str)}


@contextmanager
def state_lock(path: Path):
    """Lock the complete transaction; atomic replacement alone loses concurrent updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lockpath = path.with_name(path.name + '.lock')
    fd = os.open(lockpath, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+b') as lock:
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 0.25
        while True:
            try:
                lock.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('state lock unavailable')
                time.sleep(0.02)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def save_state(path: Path, data: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.cst-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        return False


def region_check() -> dict:
    if os.environ.get('CST_REGION_CHECK') != '1':
        return {'enabled': False, 'changed': [], 'message': '', 'observed': False, 'lookup': 'disabled'}
    try:
        with state_lock(state_path()):
            return _region_check()
    except (OSError, TimeoutError):
        return {'enabled': True, 'changed': [], 'observed': False, 'lookup': 'state_unavailable',
                'message': '状态存储暂不可用，无法可靠比较出口 IP'}


def _region_check() -> dict:
    if os.environ.get('CST_REGION_CHECK') != '1':
        return {'enabled': False, 'changed': [], 'message': '', 'observed': False, 'lookup': 'disabled'}
    ip, cc, source = get_egress()
    tz = timezone_name()
    statefile = state_path()
    previous = read_state(statefile)
    changed = []
    next_state = previous.copy()
    saved = True
    if ip is not None:
        salt = previous.get('salt') or secrets.token_hex(16)
        digest = hashlib.sha256((salt + ':' + ip).encode('utf-8')).hexdigest()
        last = previous.get('last_ip_digest')
        if last is None:
            changed.append('首次取得出口 IP')
        elif last != digest:
            changed.append('出口 IP 已变化')
        next_state['salt'] = salt
        next_state['last_ip_digest'] = digest
        if cc and cc != previous.get('country_code') and last is not None:
            changed.append('出口地区识别信息已变化')
        if cc:
            next_state['country_code'] = cc
        next_state['source'] = source
        if previous.get('timezone') and previous['timezone'] != tz:
            changed.append('设备时区已变化')
        next_state['timezone'] = tz
        next_state['last_lookup_status'] = 'observed'
        saved = save_state(statefile, next_state)
    # No IP: can check timezone as an auxiliary signal only if there was a prior observation.
    elif previous.get('last_ip_digest') and previous.get('timezone') != tz:
        changed.append('设备时区已变化（当前出口 IP 未能复查）')
        next_state['timezone'] = tz
    if ip is None:
        if previous.get('last_lookup_status') != source:
            changed.append('当前出口 IP 无法检测，无法确定是否变化')
        next_state['last_lookup_status'] = source
        saved = save_state(statefile, next_state)
    if changed:
        message = '、'.join(changed)
        country = next_state.get('country_code')
        if country and ip is not None:
            policy = read_json(REGIONS_FILE)
            supported = set(policy.get('supported_iso_3166_1_alpha_2', []))
            if supported and country not in supported:
                message += f'，地区信号 {country} 不在当前离线支持地区清单中，请核对官方规则'
    else:
        message = ''
    if not saved:
        message += '；本地状态未能保存，后续比较可能不完整'
    return {
        'enabled': True, 'changed': changed, 'message': message,
        'observed': ip is not None, 'lookup': source,
        'country_code': cc if ip is not None else None,
        'official_flag_known': False,
    }


def notice_path() -> Path:
    state = state_path()
    return state.with_name(state.name + '.notices.json')


def notification(messages: list[str], event_name: str) -> dict:
    """A user-only terminal notice; never inject detector output into Claude's context."""
    if not messages:
        return {}
    text = 'Claude 哨兵提醒：' + '；'.join(dict.fromkeys(
        ''.join(c if c.isprintable() else ' ' for c in msg).strip('；。 ') for msg in messages))
    text += '；仅供参考，不代表官方内部标记。'
    try:
        with state_lock(state_path()):
            old = read_json(notice_path()).get('notices', [])
            old = old if isinstance(old, list) else []
            old.append({'time': datetime.now(timezone.utc).isoformat(), 'event': event_name,
                        'message': text, 'delivery': 'unverified'})
            if not save_state(notice_path(), {'notices': old[-100:]}):
                text = text[:-1] + '；本地提醒记录未能保存。'
    except (OSError, TimeoutError):
        text = text[:-1] + '；本地提醒记录未能保存。'
    if event_name in ('SessionStart', 'UserPromptSubmit', 'Stop'):
        return {'systemMessage': text}
    return {'terminalSequence': '\x1b]9;' + text + '\x07'}


def hook(event: dict) -> dict:
    name = event.get('hook_event_name')
    messages = []
    if name == 'UserPromptSubmit':
        prompt = event.get('prompt', '')
        transcript = event.get('transcript_path', '')
        context = transcript_context(transcript)
        hits = analyze(prompt)
        for label in contextual_marks(prompt, context, hits):
            if label not in hits: hits.append(label)
        if hits and _new_notice('content', '\n'.join(hits[:4]), str(event.get('session_id', ''))):
            messages.append('内容标记：' + '、'.join(hits[:4]))
        if transcript and (context.get('incomplete') or (not context['available'] and not context.get('missing'))):
            if _new_notice('history_status', 'incomplete', str(event.get('session_id', ''))):
                messages.append('部分会话记录不可读，检测可能不完整')
        notice = visible_notice(prompt)
        if notice and _new_notice('user_report', prompt, str(event.get('session_id', ''))):
            messages.append('用户所述提示涉及：' + '、'.join(notice) + '，真实性未核验')
    elif name == 'Stop':
        answer = event.get('last_assistant_message', '')
        if (isinstance(answer, str) and REFUSAL.search(answer)
                and _new_notice('refusal', answer, str(event.get('session_id', '')))):
            messages.append('观察到回复可能包含安全拒绝')
        notices = visible_notice(answer)
        if notices and _new_notice('assistant_notice', answer, str(event.get('session_id', ''))):
            messages.append('可见回复涉及：' + '、'.join(notices) + '，请核对原通知')
    elif name in ('Notification', 'StopFailure'):
        parts = [event.get('title', ''), event.get('message', ''),
                 event.get('error_details', ''), event.get('last_assistant_message', '')]
        text = ' '.join(x for x in parts if isinstance(x, str))
        notices = visible_notice(text)
        if name == 'StopFailure':
            errors = {'account_on_hold': '账号限制',
                      'authentication_failed': '身份验证或访问配置异常',
                      'oauth_org_not_allowed': '组织访问限制',
                      'cloud_credential_error': '云服务凭据异常'}
            error = event.get('error')
            label = errors.get(error) if isinstance(error, str) else None
            if label and label not in notices:
                notices.append(label)
            text = str(error) + ':' + text
        if notices and _new_notice('client_notice', text, str(event.get('session_id', ''))):
            messages.append('客户端提示涉及：' + '、'.join(notices) + '，请查看原通知')
    # Do expensive history work before advancing the IP baseline.
    if name in ('SessionStart', 'UserPromptSubmit'):
        region = region_check()
        if region['message']:
            messages.insert(0, region['message'])
    # No `decision`, `continue:false`, modified prompt, or blocking exit code.
    return notification(messages, name)


def main() -> None:
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) > 1 and sys.argv[1] == '--notices':
        print(json.dumps(read_json(notice_path()), ensure_ascii=False, indent=2))
        return
    if len(sys.argv) > 1 and sys.argv[1] == '--analyze':
        print(json.dumps({'marked_topics': analyze(' '.join(sys.argv[2:]))}, ensure_ascii=False, indent=2))
        return
    if len(sys.argv) > 1 and sys.argv[1] in ('--preflight', '--region-report'):
        print(json.dumps(region_check(), ensure_ascii=False, indent=2))
        return
    try:
        event = json.load(sys.stdin)
    except (OSError, ValueError):
        event = {}
    try:
        result = hook(event if isinstance(event, dict) else {})
    except Exception:
        result = {}  # never disrupt or delay the user's conversation
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
