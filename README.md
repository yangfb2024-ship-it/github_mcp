# github_mcp

MCP server for GitHub 数据检索：搜索仓库、代码、Issue/PR、提交、用户、Topics、Labels，并可获取详情（仓库信息、README、文件内容、Issue）。

基于 **Python FastMCP**，默认通过 **Streamable HTTP** 提供远程访问。

## 工具一览

### 搜索（7 个，全部只读）

| 工具 | 端点 | 说明 |
|------|------|------|
| `github_search_repos` | `/search/repositories` | 关键词 + `language:`/`stars:`/`user:` 等 qualifier |
| `github_search_code` | `/search/code` | 代码检索，**需 token**，10 次/分 |
| `github_search_issues` | `/search/issues` | Issue 与 PR，`state:`/`label:`/`is:pr` 等 |
| `github_search_commits` | `/search/commits` | 默认分支提交检索 |
| `github_search_users` | `/search/users` | 用户/组织检索 |
| `github_search_topics` | `/search/topics` | 仓库主题检索 |
| `github_search_labels` | `/search/labels` | 标签检索（**需 `repository_id`**，来自 `github_get_repo` 的 `id` 字段） |

### 详情（4 个，只读）

| 工具 | 说明 |
|------|------|
| `github_get_repo` | 仓库详情（语言、star/fork、license、topics） |
| `github_get_repo_readme` | README 原文 |
| `github_get_file_content` | 文件内容 / 目录列表 |
| `github_get_issue` | Issue/PR 详情（含完整正文） |

## 安装

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 配置

| 环境变量 | 默认 | 说明 |
|---------|------|------|
| `GITHUB_TOKEN` | 空 | 启用 code search 并提升限速到 30 次/分 |
| `HOST` | `127.0.0.1` | HTTP 监听地址 |
| `PORT` | `8000` | HTTP 端口 |
| `MCP_TRANSPORT` | `streamable_http` | 设 `stdio` 切到本地 stdio |

```bash
cp .env.example .env   # 填入 GITHUB_TOKEN
export $(grep -v '^#' .env | xargs)
```

## 运行

```bash
# 远程（Streamable HTTP）
python -m github_mcp.server

# 本地（stdio）
MCP_TRANSPORT=stdio python -m github_mcp.server
```

客户端 MCP 配置（如 Claude Desktop / opencode）：

```json
{
  "mcpServers": {
    "github_mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## 使用示例

- 「找到 Python 写的 fastmcp 相关高星仓库」 → `github_search_repos` q=`fastmcp language:python` sort=`stars`
- 「requests 里 open 状态的 bug issue」 → `github_search_issues` q=`repo:psf/requests label:bug state:open is:issue`
  （配置了 `GITHUB_TOKEN` 时，GitHub 要求查询必须带 `is:issue` 或 `is:pull-request`）
- 「fastapi 里 argparse 在哪用到」 → `github_search_code` q=`argparse repo:fastapi/fastapi`
- 「把 fastapi 的 README 总结一下」 → `github_get_repo_readme` repo=`fastapi/fastapi`

## 设计说明

- 工具命名统一 `github_` 前缀，注解全部 `readOnlyHint=True`（纯数据检索）
- 所有 search 工具支持 `response_format=markdown|json` 双格式输出
- 分页：`per_page`(1-100) + `page`，响应带 `total_count`/`has_more`/`next_page`，单次搜索上限 1000 条
- code/issues/commits 请求 `text-match` 媒体类型，返回命中片段方便定位
- 错误信息可行动：401 → 提示配 token；403 → 提示限速/等待；422 → 提示 qualifier 语法
- token 从环境变量读取，不入代码；校验失败不会暴露内部错误
