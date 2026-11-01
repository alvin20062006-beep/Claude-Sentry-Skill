# Claude Sentry Skill · Claude 哨兵

面向 Claude 的轻量提醒工具。**正常回答优先，有明确、可观察的信号时只附加一句提醒，没有信号就不添加内容。**

不评分、不分级、不预测封号概率，不猜测官方内部标记；不改写、替代或阻断正常回答，不要求用户确认。无需额外模型服务或模型 API Key。

## 使用方式

| 方式 | 功能 |
| --- | --- |
| Claude Code Plugin | 内容主题、客户端可见通知、可选的出口 IP 变化提醒 |
| 独立 Claude Skill | 当前 Claude 根据可见上下文给出简短提醒，不自动查询 IP 或执行本地 Hooks |

两种方式共用一份规则库。提醒可在回复末尾或独立通知中显示；没有回答正文的 IP 变化和客户端错误也可独立提醒。检测失败不阻断交流。

## Claude Code Plugin

需要 Claude Code **2.1.141+**、Python **3.9+** 和 Bash；Windows 使用 Git Bash。系统通知需要兼容的终端和通知设置。

进入仓库目录，检查并临时加载：

```bash
claude plugin validate .
claude --plugin-dir .
```

退出后，下次启动时省略 `--plugin-dir` 即停止加载。避免同时注册重复的 Hooks。

### 可选：出口 IP 变化提醒

默认不查询网络。需要启用时，在启动 Claude 前设置：

```bash
# Bash / Git Bash
export CST_REGION_CHECK=1
export CST_REGION_LOOKUP=1
```

```powershell
# PowerShell
$env:CST_REGION_CHECK = '1'
$env:CST_REGION_LOOKUP = '1'
```

首次成功取得 IP 提醒一次；此后每次成功观测到变化都重新提醒，包括同国家换 IP 和 A→B→A。相同状态合理去重，查询失败会说明无法检测。检测发生在会话启动或提交消息时，不覆盖两次观测之间的变化。

启用查询后会访问 `https://ipwho.is/`，该服务会看到运行端出口 IP，不会收到聊天内容。远程开发时观测的是脚本运行端。

### 本地记录

默认状态文件为 `~/.claude/cst-local-state-v07.json`，可通过 `CST_STATE_FILE` 指定私有目录。状态保存加盐 IP 摘要，不保存原始 IP 或聊天全文；Windows 文件权限继承所在目录。

查看最近产生的提醒：

```bash
python hooks/transparency.py --notices
```

记录中的 `delivery: unverified` 表示**没有送达回执**。有记录不代表系统弹窗已显示。无头模式、SDK、部分 IDE 和终端不支持完整通知显示。

## 独立 Skill

`skills/claude-sentry-skill/` 可独立使用，包含 `SKILL.md` 和所需规则。导出上传包：

```bash
python tools/package.py --skill ../Claude-Sentry-Skill-standalone-v0.8.2.zip
```

在 Claude 的 Skills 管理界面上传并启用，可用“请用 Claude 哨兵解释这条可见通知”调用。禁用或移除即可停止使用。完整仓库 ZIP 不作为独立 Skill 上传包。

## 配套参考

可以配合 [Auwait 网络工具](https://auwait.com/network-tools/#ai) 使用。网站的评分、封号相关信息供用户独立参考，与 Claude 哨兵的标记提醒用途不同；本插件不自动访问或采用网站的评分。

## 版本与测试

当前版本：**0.8.2**。已完成 Windows 基础验证；完整客户端交互、系统弹窗和 Linux/macOS 兼容性仍待进一步验证。政策与地区数据是有日期的参考快照，不作为当前违规结论；使用时核对有效日期。

```bash
python -X utf8 -B -m unittest discover -s tests -v
python tools/package.py --full ../Claude-Sentry-Skill-v0.8.2-full.zip
```

许可证：[MIT](LICENSE)。
