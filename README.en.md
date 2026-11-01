<div align="center">

<img src="docs/assets/banner.svg" alt="Claude Sentry Skill — Your conversation comes first. A heads-up when it matters." width="100%">

<br>

<img src="docs/assets/sentry.svg" alt="Sentry Notice icon" width="64" height="64">

**Your conversation comes first. A heads-up when it matters.**<br>
**让 Claude 专注回答，让哨兵轻声提醒。**

<p>
  <a href="https://github.com/alvin20062006-beep/Claude-Sentry-Skill"><img src="https://img.shields.io/badge/version-0.9.0-C56543?style=flat-square" alt="Version 0.9.0"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Claude_Code-2.1.141%2B-292724?style=flat-square" alt="Claude Code 2.1.141+"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Python-3.9%2B-427568?style=flat-square" alt="Python 3.9+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-84735A?style=flat-square" alt="MIT license"></a>
</p>

[简体中文](README.md) · **English**<br>
[Website](https://alvin20062006-beep.github.io/Claude-Sentry-Skill/?lang=en) · [Quick start](#quick-start) · [Standalone Skill](#standalone-skill) · [FAQ](#faq)

</div>

---

## ✦ Meet Claude Sentry

**Claude Sentry Skill is a lightweight advisory companion for Claude, available as a Claude Code Plugin and a standalone Skill.** When there is a clear, observable signal, it adds one short notice alongside the normal response. With no signal, it adds nothing.

> **The normal response always comes first.** No scores, risk levels, ban probabilities, or guesses about internal account flags. No rewriting, replacing, pausing, or blocking the response. No extra confirmation steps.

| What matters | What Sentry does |
| :--- | :--- |
| 💬 Keep the conversation flowing | Claude answers normally; a notice is just one extra sentence |
| 🔎 Observable evidence | Uses visible content, client events, and enabled environment observations |
| 🌐 Outbound IP changes | A new notice for every successfully observed change, including same-country changes and A→B→A |
| 🤫 Less repetition | Deduplicates unchanged signals and stays quiet without a new signal |
| 🧩 Two ways to use it | Plugin and standalone Skill share one core rule library |
| 🪶 Lightweight by design | Python standard library Hooks; no extra model, database, or model API key |

## ◉ What does a notice look like?

This is an **illustration**, not an actual client screenshot. The English notice below is a translation of the example:

```text
Claude's normal answer
────────────────────────────────────────────────────────
This function loops through the items, adds their prices,
and returns the total.

Additional notice (only with a matching signal)
────────────────────────────────────────────────────────
Claude Sentry: An outbound IP change was detected; this is
for reference and does not indicate an internal account flag.
```

Without a signal, only the normal response remains—no “no notice needed” placeholder. IP changes or client errors may trigger a standalone Hook notice even when Claude has no answer to generate. Display behavior depends on the client and terminal.

<a id="quick-start"></a>

## ⚡ Quick start

**Requirements:** Claude Code **2.1.141+**, Python **3.9+**, and Bash. Use Git Bash on Windows.

```bash
git clone https://github.com/alvin20062006-beep/Claude-Sentry-Skill.git
cd Claude-Sentry-Skill
claude plugin validate .
claude --plugin-dir .
```

This loads the plugin for that launch. To stop loading it, quit and omit `--plugin-dir` on the next launch. Avoid registering the same Hooks twice.

### Persistent installation

```bash
claude plugin marketplace add alvin20062006-beep/Claude-Sentry-Skill
claude plugin install sentry-notice@sentry-notice-marketplace
```

Restart Claude Code after installation. Do not also load the same plugin with `--plugin-dir`. Uninstall with `claude plugin uninstall sentry-notice@sentry-notice-marketplace`. These commands require a repository revision containing the marketplace manifest.

### Content detection scope

Fraud prevention questions such as “How do I recognize scam calls?” do not trigger a content notice by themselves. Ban notices target requests for operational evasion (for example, “Write a script to bypass an account ban”), not general reasons, prevention, or appeals. An educational phrase does not exempt another actionable request in the same message. Hooks still use local regular expressions, so false positives and missed paraphrases remain possible; other existing topic notices are unchanged. Visible client restriction notices are handled separately.

### Optional: enable outbound IP notices

**Network lookups are off by default.** To enable them, set these variables before starting Claude:

<details>
<summary><b>Bash / Git Bash</b></summary>

```bash
export CST_REGION_CHECK=1
export CST_REGION_LOOKUP=1
claude --plugin-dir .
```

</details>

<details>
<summary><b>PowerShell</b></summary>

```powershell
$env:CST_REGION_CHECK = '1'
$env:CST_REGION_LOOKUP = '1'
claude --plugin-dir .
```

</details>

The first successful IP observation produces a notice. Every subsequent successfully observed change produces a fresh notice. Failed lookups report that detection is unavailable and preserve the previous baseline. Checks run at session start or prompt submission; this is **not continuous monitoring** and cannot recover unobserved changes between checks.

Enabling lookups contacts `https://ipwho.is/`. The service sees the outbound IP of the machine running the script, never the chat contents. In remote environments, the observed IP belongs to the remote runtime.

<a id="standalone-skill"></a>

## 🧩 Standalone Skill

Use [`skills/claude-sentry-skill/`](skills/claude-sentry-skill/) independently of Claude Code. Export an upload package:

```bash
python tools/package.py --skill ../Claude-Sentry-Skill-standalone-v0.9.0.zip
```

Upload and enable it in a Claude interface that supports custom Skills. You can invoke it with **“Use Claude Sentry to explain this visible notice.”** Disable or remove it to stop using it. The full repository ZIP is not the standalone Skill upload package.

| Capability | Claude Code Plugin | Standalone Claude Skill |
| :--- | :--- | :--- |
| Brief notices based on visible content | ✓ | ✓ |
| Shared core rules | ✓ | ✓ |
| Automatic local Hooks | ✓ | — |
| Outbound IP lookup | When enabled by the user | — |
| Observe client Hook events | ✓ | — |
| Read local conversation records | Only records provided by Claude Code | — |

The standalone Skill is invoked by the user or loaded by Claude when relevant. **It is not guaranteed to run on every turn.** The current Hook notice text is Chinese; the bilingual documentation and website do not change runtime language behavior.

## 🔐 Privacy & local records

- Default state file: `~/.claude/cst-local-state-v07.json`. Use `CST_STATE_FILE` to choose a private directory.
- Stores a salted IP digest and limited notice state, not raw IP addresses or full chat text.
- On Windows, permissions are inherited from the containing directory; choose an appropriately private location.
- `delivery: unverified` in a local notice record means there is no delivery receipt. It **does not prove a system notification was displayed**. Headless mode, SDKs, some IDEs, and some terminals do not support the full notification experience.

```bash
# Inspect recent generated notices
python hooks/transparency.py --notices
```

<a id="faq"></a>

## ❔ FAQ

<details>
<summary><b>Does this score accounts or expose Claude's internal risk decisions?</b></summary>

No. It only provides notices about clear, observable signals. It does not supply scores, risk levels, ban probabilities, or internal flags. A notice is not a violation finding, and silence is not a safety guarantee.

</details>

<details>
<summary><b>Does it change normal answers or require a local model?</b></summary>

The rules prioritize the normal response. Notices must be additional or standalone and must not replace the answer. Hook failures must not interrupt normal conversation. The current Claude interprets visible context; Hooks use deterministic local rules without an additional LLM or local model.

</details>

<details>
<summary><b>Can I use it alongside Auwait's network tools?</b></summary>

Yes. [Auwait network tools](https://auwait.com/network-tools/#ai) can provide a separate reference for the user. Its scoring and account-ban information serve a different purpose from Sentry's advisory notices. This plugin does not automatically access or adopt that site's scores.

</details>

<details>
<summary><b>Are the policy and region data live?</b></summary>

No. They are dated reference snapshots. Check their effective dates; do not treat them as a current violation finding. The project does not provide appeals, account recovery, or definitive explanations of account bans.

</details>

## ✓ Verification status

**v0.9.0: 55 automated tests passed on cloud Linux; Claude Code 2.1.316 plugin and marketplace validation passed without warnings; local persistent installation passed with an isolated configuration. Windows was not retested for this change.**

Full client interactions, actual system notification delivery, Linux/macOS compatibility, and the standalone Skill upload experience still need further validation. Unverified behavior is not presented as complete.

```bash
# Run tests
python -X utf8 -B -m unittest discover -s tests -v

# Export the complete project
python tools/package.py --full ../Claude-Sentry-Skill-v0.9.0-full.zip
```

---

<div align="center">

**Keep the conversation going. Let the right notice find you.**<br>
If this project helps, a **Star ⭐** is welcome.

[Website](https://alvin20062006-beep.github.io/Claude-Sentry-Skill/?lang=en) · [Report an issue](https://github.com/alvin20062006-beep/Claude-Sentry-Skill/issues) · [MIT License](LICENSE)

An independent project for Claude. Not affiliated with Anthropic.

</div>
