# Feishu Pipeline Notify

把 GitHub Actions 流水线的运行结果，以**飞书自建应用私聊卡片**推送给指定用户。

- 成功 / 失败用**绿 / 红卡片**区分；
- **标题直接带仓库 + 流水线名 + 状态**，一眼定位是哪个仓库的哪条 CI；
- 失败时自动补上**失败位置**（哪个 job 的哪个 step 挂了）；
- 展示分支 / Tag、触发者、**commit（SHA + message + 作者）**、**开始 / 结束时间与耗时**；
- 走飞书 IM API（自建应用换 `tenant_access_token` → 发 `interactive` 卡片），**私聊**而非群消息。

## 用法

典型场景是用一个 `workflow_run` 工作流集中监听各流水线完成事件，再调用本 action：

```yaml
# .github/workflows/repo-notify.yml
name: Repo Notify
on:
  workflow_run:
    workflows: [CI, Release]   # 填你各顶层 workflow 的 name（不是文件名）
    types: [completed]
permissions:
  contents: read
  actions: read                # 读 jobs API 拿失败位置所需
jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: yuebai-blast/feishu-notify-action@v1
        with:
          app_id: ${{ secrets.FEISHU_APP_ID }}
          app_secret: ${{ secrets.FEISHU_APP_SECRET }}
          receive_id: ${{ secrets.FEISHU_RECEIVE_ID }}
          status:         ${{ github.event.workflow_run.conclusion }}
          workflow_name:  ${{ github.event.workflow_run.name }}
          repo:           ${{ github.repository }}
          branch:         ${{ github.event.workflow_run.head_branch }}
          event:          ${{ github.event.workflow_run.event }}
          actor:          ${{ github.event.workflow_run.actor.login }}
          run_url:        ${{ github.event.workflow_run.html_url }}
          run_id:         ${{ github.event.workflow_run.id }}
          commit_sha:     ${{ github.event.workflow_run.head_sha }}
          commit_message: ${{ github.event.workflow_run.head_commit.message }}
          commit_author:  ${{ github.event.workflow_run.head_commit.author.name }}
          run_started_at: ${{ github.event.workflow_run.run_started_at }}
          run_updated_at: ${{ github.event.workflow_run.updated_at }}
          github_token:   ${{ github.token }}
          # timezone: America/Los_Angeles   # 默认 Asia/Shanghai
```

> `workflow_run` 只能监听**本仓库**的流水线，所以每个仓库都要放一份这样的薄 workflow；但**通知逻辑只在本 action 里**，改一处、各仓库用 `@v1` 自动跟随。

## 需要的 secrets

| Secret | 说明 |
| :-- | :-- |
| `FEISHU_APP_ID` | 飞书自建应用 App ID（`cli_...`） |
| `FEISHU_APP_SECRET` | 应用 App Secret |
| `FEISHU_RECEIVE_ID` | 接收人 ID，默认按 `open_id`（注意 open_id 是**每个应用各自独立**的） |

飞书侧前置：应用需开启「机器人」能力 + 申请 `im:message` 权限并发布版本。

## inputs

见 [`action.yml`](./action.yml)。机密用 `app_id / app_secret / receive_id`，其余字段一般直接接 `github.event.workflow_run.*`。`receive_id_type` 可改为 `email` 等；`timezone` 用 IANA 名。

## 版本

- 用 `@v1` 引用浮动主版本，自动获得 `v1.x` 的修复；
- 需要锁定则用 `@v1.0.0` 等精确 tag。
