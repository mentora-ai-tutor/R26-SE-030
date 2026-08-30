# GitHub Calling Methods: MCP and HTTP

| Field | Value |
|---|---|
| Scope | GitHub calls made after a student connects GitHub |
| Primary method | MCP connector feature |
| Secondary method | Direct HTTP fallback to GitHub REST/OAuth APIs |
| Token owner | `services/user service/` |

This codebase uses the **MCP connecting feature** as the preferred way to call GitHub from analysis or agent workflows. The **HTTP flow has already been set up as the fallback method** for OAuth handshakes, token revocation, and cases where an MCP connector does not expose the exact GitHub operation needed.

---

## 1. Common Auth Token Flow

Both methods depend on the same GitHub access token.

1. The frontend starts linking with `GET /api/github/oauth/start`.
2. GitHub redirects back to `GET /api/github/oauth/callback`.
3. `services/user service/src/utils/ghClient.js` exchanges the OAuth `code` for an `access_token`.
4. `services/user service/src/controllers/githubOAuth.controller.js` encrypts the token and stores it in `GithubCredential`.
5. Internal services can fetch the decrypted token from:

```txt
GET /api/internal/github/credential/:studentId
```

The token should not be exposed to the frontend. It should only be used server-side by trusted services such as knowledge analysis, repo review, or an MCP connector session.

---

## 2. Method 1: MCP Connector Feature

MCP means Model Context Protocol. In this approach, the application does not manually build every GitHub REST URL. Instead, it calls a GitHub MCP connector/tool server, and that connector performs the GitHub API calls using the student's auth token.

This is the major/preferred method for this codebase because it fits agentic workflows better:

- The LLM or analysis worker can call structured tools such as list repositories, read files, inspect commits, or fetch pull request data.
- GitHub API details stay inside one connector boundary.
- Tool permissions can be allowlisted.
- The app can keep GitHub access consistent across multiple analysis features.

### MCP Flow

```txt
Student links GitHub
        |
        v
user-service stores encrypted token
        |
        v
knowledge-analysis requests token through internal API
        |
        v
MCP GitHub connector is opened with that token
        |
        v
analysis workflow calls MCP GitHub tools
        |
        v
normalized repo/commit/file data is returned to the service
```

### Implementation Shape

Use a wrapper around the MCP client so the rest of the app does not depend on raw connector/tool names.

```ts
// Pseudo-code: exact SDK and tool names depend on the MCP GitHub connector.
async function withGithubMcp(studentId: string, work: (client: McpClient) => Promise<unknown>) {
  const credential = await userService.getGithubCredential(studentId);

  const client = await createGithubMcpClient({
    authToken: credential.access_token,
    allowedTools: [
      "repos.list",
      "repos.get",
      "commits.list",
      "contents.read",
    ],
  });

  try {
    return await work(client);
  } finally {
    await client.close();
  }
}
```

Example usage:

```ts
await withGithubMcp(studentId, async (github) => {
  const repos = await github.callTool("repos.list", { visibility: "all" });
  const commits = await github.callTool("commits.list", {
    owner: "owner",
    repo: "repo",
    since: "2026-01-01T00:00:00Z",
  });

  return { repos, commits };
});
```

### Important MCP Token Rules

- Use a per-student token for student repo analysis.
- Do not share one long-lived MCP GitHub session across different students.
- Prefer a short-lived connector session per analysis job, or use an MCP server that supports safe per-request auth context.
- Allowlist the GitHub tools that the feature actually needs.
- Log tool names and request IDs, but never log the access token.
- Normalize MCP output before passing it into scoring or LLM prompts.

Use MCP for:

- Repository listing and selection.
- Reading commit history.
- Reading source files for repo review.
- Future agentic GitHub workflows where the model needs structured tool access.

---

## 3. Method 2: Direct HTTP Fallback

Direct HTTP means the service calls GitHub endpoints itself using `axios`, `httpx`, `fetch`, or another HTTP client. In this codebase, this flow is already set up and should be treated as the fallback method after the MCP connector path.

This codebase already uses direct HTTP in two places:

- `services/user service/src/utils/ghClient.js` exchanges OAuth codes, fetches the GitHub viewer, and revokes grants.
- `services/knowledge-analysis/app/services/github_fetcher.py` fetches commits from GitHub REST using a token.

Direct HTTP remains useful when:

- The operation is part of OAuth, such as token exchange or grant revocation.
- The MCP connector does not expose the required endpoint.
- The service needs custom pagination, caching, retries, or rate-limit handling.
- A simple deterministic call is easier than opening an MCP session.

### HTTP Flow

```txt
Service receives or loads GitHub access token
        |
        v
Service builds GitHub REST URL
        |
        v
Service sends Authorization header
        |
        v
Service handles status codes, pagination, and rate limits
        |
        v
Service normalizes response data
```

### Node/Express Example

```js
const axios = require("axios");

async function getViewer(accessToken) {
  const response = await axios.get("https://api.github.com/user", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    timeout: 10000,
  });

  return {
    id: response.data.id,
    login: response.data.login,
  };
}
```

### Python/FastAPI Example

```py
import httpx

async def get_commits(access_token: str, owner: str, repo: str):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers, params={"per_page": 100})

    if response.status_code == 401:
        raise Exception("GitHub token is invalid or expired")
    if response.status_code == 403:
        raise Exception("GitHub forbidden or rate limited")
    if response.status_code == 404:
        raise Exception("Repository not found or token has no access")

    response.raise_for_status()
    return response.json()
```

### HTTP Token Rules

- Send the token only in the `Authorization` header.
- Prefer `Bearer <token>` for OAuth and fine-grained tokens.
- Never place the token in URLs, query strings, logs, or frontend state.
- Handle `401`, `403`, `404`, `429`, and `5xx` explicitly.
- Respect GitHub pagination and rate-limit headers.
- Convert GitHub response data into internal DTOs before analysis.

---

## 4. Which Method To Use

| Need | Preferred method | Reason |
|---|---|---|
| OAuth code exchange | HTTP | OAuth is a low-level GitHub endpoint, already implemented in user-service. |
| Token revocation/unlink | HTTP | GitHub grant revocation is deterministic and user-service owned. |
| Repo listing for analysis | MCP | Fits connector-based agent workflow. |
| Commit/file inspection for repo review | MCP | Lets the analysis worker use structured GitHub tools. |
| Unsupported GitHub endpoint | HTTP | Use REST directly when no MCP tool exists. |
| Highly custom pagination/cache behavior | HTTP | Service controls all request and retry behavior. |

The rule for this codebase is: **use MCP first for GitHub data access in analysis workflows; use HTTP for OAuth, fallback, and low-level operations.**

---

## 5. Codebase Mapping

| Area | Current file | Role |
|---|---|---|
| OAuth start/callback/status/unlink | `services/user service/src/controllers/githubOAuth.controller.js` | Owns GitHub linking flow and encrypted token persistence. |
| GitHub HTTP client | `services/user service/src/utils/ghClient.js` | Exchanges OAuth code, fetches viewer, revokes grant. |
| Token encryption | `services/user service/src/utils/ghCrypto.js` | Encrypts/decrypts GitHub token with AES-256-GCM. |
| Token storage | `services/user service/src/models/GithubCredential.js` | Stores encrypted per-student GitHub credential. |
| Internal token access | `services/user service/src/controllers/internal.controller.js` | Serves decrypted token to trusted internal services. |
| Existing REST fetcher | `services/knowledge-analysis/app/services/github_fetcher.py` | Direct HTTP fallback/client for commit fetching. |

Future GitHub analysis code should put MCP access behind a service wrapper, for example:

```txt
services/knowledge-analysis/app/services/github_mcp_client.py
```

That wrapper should accept a student ID, load the token through the internal credential endpoint, open a per-student MCP GitHub session, call the allowed tools, and return normalized data to the analysis pipeline.
