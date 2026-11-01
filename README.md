<div align="center">

<img src="docs/assets/banner.svg" alt="Claude Sentry Skill · Claude 哨兵 — 正常回答优先，提醒恰到好处。" width="100%">

<br>

<img src="docs/assets/sentry.svg" alt="Sentry Notice icon" width="64" height="64">

**让 Claude 专注回答，让哨兵轻声提醒。**<br>
**Your conversation comes first. A heads-up when it matters.**

<p>
  <a href="https://github.com/alvin20062006-beep/Claude-Sentry-Skill"><img src="https://img.shields.io/badge/version-0.9.1-C56543?style=flat-square" alt="Version 0.9.1"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Claude_Code-2.1.141%2B-292724?style=flat-square" alt="Claude Code 2.1.141+"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Python-3.9%2B-427568?style=flat-square" alt="Python 3.9+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-84735A?style=flat-square" alt="MIT license"></a>
</p>

**简体中文** · [English](README.en.md)<br>
[项目主页](https://alvin20062006-beep.github.io/Claude-Sentry-Skill/) · [快速开始](#quick-start) · [独立 Skill](#standalone-skill) · [常见问题](#faq)

</div>

---

## ✦ 一句话认识 Claude 哨兵

**Claude Sentry Skill 是专门面向 Claude 的轻量提醒工具，提供 Claude Code Plugin 和独立 Skill 两种用法。** 发现明确、可观察的信号时，在正常回答之外补充一句简短提醒；没有信号，就不增加任何内容。

> **正常回答永远优先。** 不评分、不分级、不估算封号概率，不猜测官方内部标记；不改写、替代、暂停或阻断回答，不要求用户确认。

| 你关心的事 | Claude 哨兵的做法 |
| :--- | :--- |
| 💬 保持对话流畅 | Claude 照常回答，提醒只作为额外的一句话 |
| 🔎 看得见的依据 | 依据可见内容、客户端事件与已启用的环境观测提醒 |
| 🌐 出口 IP 变化 | 每次成功观测到变化都提醒，包括同国家换 IP、A→B→A |
| 🤫 避免重复打扰 | 同一信号合理去重，没有新信号就保持安静 |
| 🧩 两种使用方式 | Plugin 与独立 Skill 共用一份核心规则 |
| 🪶 轻量运行 | Hook 使用 Python 标准库，无额外模型、数据库或模型 API Key |

## ◉ 提醒是什么样的？

下面是**交互示意**，不是实际客户端截图：

```text
Claude 的正常回答
────────────────────────────────────────────────────────
这个函数会遍历商品列表，将每项商品的价格相加后返回总额。

额外提醒（仅在出现对应信号时）
────────────────────────────────────────────────────────
Claude 哨兵提醒：检测到出口 IP 已变化，仅供参考，不代表官方内部标记。
```

没有信号时，只保留正常回答，不输出“无需提醒”等占位内容。IP 变化、客户端错误等事件没有回答正文时，允许 Hook 独立提醒。提醒的显示方式取决于客户端和终端支持。

<a id="quick-start"></a>

## ⚡ 快速开始

**环境要求：** Claude Code **2.1.141+**、Python **3.9+**、Bash。Windows 使用 Git Bash。

```bash
git clone https://github.com/alvin20062006-beep/Claude-Sentry-Skill.git
cd Claude-Sentry-Skill
claude plugin validate .
claude --plugin-dir .
```

这是临时加载方式；退出后，下次启动时省略 `--plugin-dir` 即停止加载。避免重复注册同一套 Hooks。

### 持久安装

```bash
claude plugin marketplace add alvin20062006-beep/Claude-Sentry-Skill
claude plugin install sentry-notice@sentry-notice-marketplace
```

安装后重启 Claude Code，不要再用 `--plugin-dir` 重复加载。卸载命令：`claude plugin uninstall sentry-notice@sentry-notice-marketplace`。以上命令需要仓库已包含本次新增的 marketplace 配置。

### 内容提醒的范围

“怎么识别诈骗电话？”等反诈科普问题不因诈骗词汇本身触发内容提醒。封禁相关规则针对“帮我写一个绕过封号的脚本”等操作请求；“Claude 为什么会封号”、合规预防和申诉的一般讨论不因封号词汇触发。同一消息中的科普表达不会豁免另一项操作请求。Hook 使用正则和局部语句中的行为、目标、用途组合线索，**不是语义意图理解**。例如“仿冒银行登录页＋收集密码”“伪造＋证件”“电话话术＋欺骗＋转账”会产生具体类别提醒，而不是仅依赖“诈骗”一词。组合线索不跨句拼接，但仍可能误判引用、否定、授权演练，也会漏掉隐晦或未覆盖的表达；其他已有主题提醒保持原有范围。客户端实际显示的限制通知单独处理。

### 可选：开启出口 IP 变化提醒

**默认不查询网络。** 需要时，在启动 Claude 之前设置：

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

首次成功取得 IP 提醒一次；此后每次成功观测到变化都重新提醒。查询失败会提示无法检测，并保留已有基线。检测发生在会话启动或提交消息时，**不是持续监控**，不会补报两次观测之间未被观察到的变化。

启用查询后会访问 `https://ipwho.is/`。该服务会看到脚本运行端的出口 IP，不会收到聊天内容；在远程环境运行时，观察的是远程运行端。

<a id="standalone-skill"></a>

## 🧩 独立 Skill

不使用 Claude Code 时，可独立使用 [`skills/claude-sentry-skill/`](skills/claude-sentry-skill/)。导出上传包：

```bash
python tools/package.py --skill ../Claude-Sentry-Skill-standalone-v0.9.1.zip
```

在支持自定义 Skills 的 Claude 界面上传并启用，可主动调用：**“请用 Claude 哨兵解释这条可见通知。”** 禁用或移除即可停止使用；完整仓库 ZIP 不作为独立 Skill 上传包。

| 能力 | Claude Code Plugin | 独立 Claude Skill |
| :--- | :--- | :--- |
| 根据可见内容提供简短提醒 | ✓ | ✓ |
| 共用核心规则库 | ✓ | ✓ |
| 自动执行本地 Hooks | ✓ | — |
| 查询出口 IP | 用户启用后 | — |
| 观察客户端 Hook 事件 | ✓ | — |
| 读取本地会话记录 | 仅 Claude Code 提供的记录 | — |

独立 Skill 由用户调用或由 Claude 按相关性加载，**不保证每轮自动执行**。

## 🔐 隐私与本地记录

- 默认状态文件：`~/.claude/cst-local-state-v07.json`；可用 `CST_STATE_FILE` 指定私有目录。
- 保存加盐 IP 摘要和少量提醒状态，不保存原始 IP 或聊天全文。
- Windows 文件权限继承所在目录，应将状态文件放在适当的私有目录。
- 本地提醒记录中的 `delivery: unverified` 表示没有送达回执，**不代表系统弹窗已显示**。无头模式、SDK、部分 IDE 和终端不支持完整通知显示。

```bash
# 查看最近产生的提醒
python hooks/transparency.py --notices
```

<a id="faq"></a>

## ❔ 常见问题

<details>
<summary><b>这是评分工具，或者能知道 Claude 的内部风控吗？</b></summary>

不是。项目只对明确、可观察的信号作提醒，不提供评分、风险等级、封号概率或后台标记。出现提醒不代表违规，没有提醒也不是安全保证。

</details>

<details>
<summary><b>会改变 Claude 的正常输出吗？需要本地模型吗？</b></summary>

规则要求正常回答优先，提醒只能附加或独立显示，不能替代正文。Hook 检测失败不得影响正常交流。内容解释由当前 Claude 完成，Hook 使用本地确定性规则，不连接额外 LLM 或本地模型。

</details>

<details>
<summary><b>可以与 Auwait 网络工具一起用吗？</b></summary>

可以配合 [Auwait 网络工具](https://auwait.com/network-tools/#ai) 使用。网站的评分、封号相关信息供用户独立参考，与本项目的标记提醒用途不同；本插件不自动访问或采用网站的评分。

</details>

<details>
<summary><b>政策和地区数据是实时的吗？</b></summary>

不是。它们是有日期的参考快照，使用时需核对有效日期，不直接作为当前违规结论。项目不提供申诉、账号恢复或封号原因判定功能。

</details>

## ✓ 当前验证状态

**v0.9.1：63 项自动化测试通过（云端 Linux），Claude Code 2.1.316 插件与 marketplace 校验无警告，隔离配置下本地持久安装通过。本次未复测 Windows。**

完整客户端交互、系统弹窗实际送达、Linux/macOS 兼容性及独立 Skill 上传体验仍待补充验证。未经实际验证的行为不作为完成承诺。

```bash
# 测试
python -X utf8 -B -m unittest discover -s tests -v

# 导出完整项目
python tools/package.py --full ../Claude-Sentry-Skill-v0.9.1-full.zip
```

---

<div align="center">

**让对话继续，让提醒到位。**<br>
如果这个项目对你有帮助，欢迎点一颗 **Star ⭐**。

[项目主页](https://alvin20062006-beep.github.io/Claude-Sentry-Skill/) · [反馈问题](https://github.com/alvin20062006-beep/Claude-Sentry-Skill/issues) · [MIT License](LICENSE)

面向 Claude 的独立项目，与 Anthropic 无隶属关系。

</div>
