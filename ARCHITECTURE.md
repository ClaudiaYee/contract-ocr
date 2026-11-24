# 合同平台整体架构（华为云 Web 版）

> 本文档说明 contract-ocr 从「Windows 单机桌面工具」升级为「华为云上的多用户网页平台」的底层框架与已确定的设计决策。
> 图使用 Mermaid 绘制，GitHub 会直接渲染。新对话或新成员阅读本文即可了解全貌。
> 基线代码：`feature/merge-list-edit-uploader`（v2.15.0）。

---

## 1. 目标

| 能力 | 说明 |
|---|---|
| 项目池与上传权限 | 先选项目 Code，系统显示该 Code 的 EIC；只有该 Code 登记的 EIC / PIC / 小秘书可以上传 |
| 合同库与检索 | 上传后 OCR、识别关键词与标签；所有人可检索，原文只对上传者本人可见 |
| AI 对话式 SOW 生成 | SOC 合同：对话收齐字段后按固定模板生成；其他合同：参考历史合同 + 公开资料 + 对话确认的信息起草 |
| 角色权限 | 管理员 / 项目池维护人员 / SOW 使用人员（小秘书端） |
| 部署 | 华为云，内部人员通过浏览器使用 |

---

## 2. 总体架构

```mermaid
flowchart TB
    subgraph Client["浏览器（内部人员）"]
        UI_UP["上传识别 / 我的合同"]
        UI_SEARCH["合同检索（小秘书端）"]
        UI_SOW["AI 对话 · SOW 生成"]
        UI_ADMIN["项目池 / 用户与权限管理"]
    end

    SSO["公司统一登录 SSO<br/>（待确认接入方式）"]

    subgraph HWC["华为云 VPC"]
        GW["ELB + WAF<br/>HTTPS 入口"]

        subgraph App["应用层（ECS / CCE 容器）"]
            WEB["Web 前端<br/>复用 index.html + js/"]
            API["API 服务<br/>统一鉴权与权限校验"]
            AUTH["认证与角色模块"]
            POOL["项目池模块"]
            CONTRACT["合同模块<br/>上传 / 字段白名单 / 原文权限"]
            SEARCH["检索模块<br/>关键词 + 全文命中 + 向量"]
            SOW["SOW 生成模块<br/>分流 / SOC 填表 / 其他合同起草"]
            GUARD["防原文泄露检查<br/>脱敏 + 相似度比对"]
            AUDIT["审计日志"]
        end

        subgraph Worker["后台任务层"]
            OCR["OCR 任务服务<br/>复用 native/ 下 OCR、去印章、日期复核<br/>（保留断网）"]
            ANALYZE["分析任务<br/>关键词 / Tag / 甲乙方 / 条款切分 / 脱敏"]
        end

        subgraph Data["数据层"]
            RDS[("RDS 数据库<br/>用户 / 项目池 / 合同信息 / 权限 / 会话")]
            OBS[("OBS 对象存储<br/>合同原件，服务端加密")]
            IDX[("检索库<br/>全文 + 向量（存脱敏条款）")]
            TPL[("SOC 模板<br/>Word 模板及条件规则")]
        end
    end

    MAAS["ModelArts Studio MaaS<br/>大模型 API（IP 白名单）"]
    WEBSEARCH["联网搜索 API<br/>只发送公司名称等公开查询词"]

    Client --> GW --> WEB
    GW --> API
    API --> SSO
    API --> AUTH & POOL & CONTRACT & SEARCH & SOW
    CONTRACT --> OBS
    CONTRACT --> OCR --> ANALYZE --> IDX
    ANALYZE --> RDS
    AUTH & POOL & CONTRACT --> RDS
    SEARCH --> RDS & IDX
    SOW --> SEARCH
    SOW --> TPL
    SOW --> MAAS
    SOW --> WEBSEARCH
    SOW --> GUARD
    API --> AUDIT --> RDS
```

**原则**

1. 所有权限判断都在 **API 服务端** 完成；前端置灰按钮只是提示。
2. 返回其他人合同的接口一律经过 **字段白名单**，原文永远不会发到非上传者的浏览器。
3. AI 只读取 **脱敏后的条款**；生成结果经过 **相似度检查** 才返回。
4. 发往外网（联网搜索）的只有公开查询词，**绝不包含合同内容**。

---

## 3. 现有代码如何迁移

| 现有代码 | 平台化后 | 处理方式 |
|---|---|---|
| `index.html`、`css/`、`js/app.js`、`js/vault.js` 等前端 | Web 前端 | 复用；数据来源由本机服务改为平台 API |
| `js/extractor.js`、`js/keywords.js`、`js/service-content.js`、`js/contract-scope.js`、`js/audit-review.js` | 分析任务 | 复用规则；在服务端（Node）或浏览器运行，结果写入数据库 |
| `native/engine.py`、`native/documents.py`、`native/stamp_removal.py`、`native/date_review.py` 等 | OCR 任务服务 | 复用；改为从任务队列取文件 |
| `native/offline_guard.py` | OCR 任务服务 | 只保留在 OCR 进程上 |
| `native/desktop.py` 的本机 JSON 存储 | RDS + OBS | 重写为数据库访问 |
| `native/excel_table.py` 云盘 Excel 总表、合并逻辑 | 合同库 | 总表不再需要；`COLUMNS` 定义沿用为「他人合同可见字段白名单」；导出 Excel 功能保留 |
| `native/fulltext_index.py` 布隆过滤器加密索引 | 检索模块 | 不再需要；服务端直接判断全文是否包含搜索词，只返回命中的词 |
| 上传者 ID 取 Windows 账户名 | 登录账号 | 由认证模块提供 |

---

## 4. 角色与权限（已确定）

### 4.1 规则

| 规则 | 内容 |
|---|---|
| 上传 | 只有项目池中登记在该 Code 下、角色为 **EIC / PIC / 小秘书** 的账号可上传 |
| 查看原文 | **只有上传者本人**（查看全文、下载原件、定位到识别全文） |
| 他人合同 | 所有人只读查看基本信息，字段同小秘书端「合同检索」（见 6.2） |
| AI 参考 | 所有合同（脱敏版本）都可被 AI 检索参考，界面不显示他人原文 |
| 管理员 | 只管理用户、角色、Code 与人员关系、SOC 模板；**不能查看原文，也不因管理员身份获得上传权限** |

> 待确认：同一 Code 的 EIC / PIC / 小秘书之间是否可互相查看原文。当前按严格规则（仅上传者本人）实现；放宽只需修改 `can_view_original`。

### 4.2 角色权限矩阵

| 权限点 | 管理员 | 项目池维护人员 | SOW 使用人员（小秘书端） |
|---|---|---|---|
| 管理用户、角色、Code 与人员关系 | ✓ | | |
| 配置 SOC 模板 | ✓ | | |
| 录入 / 更新项目池 | | ✓（授权范围内） | |
| 上传合同 | 仅当本人是该 Code 的 EIC/PIC/小秘书 | 同左 | 同左 |
| 查看自己上传的合同原文 | ✓ | ✓ | ✓ |
| 查看他人合同原文 | ✗ | ✗ | ✗ |
| 检索、查看他人合同基本信息 | ✓ | ✓ | ✓ |
| AI 对话生成 SOW | | ✓ | ✓ |

### 4.3 服务端校验

```python
UPLOAD_ROLES = {'EIC', 'PIC', '小秘书'}

def can_upload(user, code):
    return db.exists(
        "SELECT 1 FROM project_members WHERE code = %s AND user_id = %s AND role = ANY(%s)",
        code, user.id, list(UPLOAD_ROLES))

def can_view_original(user, contract):
    return contract.uploaded_by == user.id   # 管理员也不例外
```

---

## 5. 数据模型

```mermaid
erDiagram
    users ||--o{ user_roles : "拥有"
    users ||--o{ project_members : "登记于"
    projects ||--o{ project_members : "包含"
    projects ||--o{ contracts : "归属"
    users ||--o{ contracts : "上传"
    contracts ||--o{ clauses : "切分为"
    users ||--o{ sow_sessions : "发起"
    soc_templates ||--o{ sow_sessions : "使用"
    users ||--o{ audit_logs : "产生"

    users {
        string id PK
        string name
        string email
    }
    user_roles {
        string user_id FK
        string role "管理员 / 项目池维护 / SOW使用"
    }
    projects {
        string code PK
        string project_name
        string client_name
        bool is_c1 "C1 来源待确认"
        string service_type
    }
    project_members {
        string code FK
        string user_id FK
        string role "EIC / PIC / 小秘书"
    }
    contracts {
        string id PK
        string code FK
        string uploaded_by FK
        string obs_key "原件位置"
        string project_name
        string party_a
        string party_b
        date signed_at
        string keywords
        string service_domain
        string specific_service
        string systems
        string engagement_name
        text raw_text "仅上传者可读"
    }
    clauses {
        string id PK
        string contract_id FK
        string clause_type "测试范围 / 测试指标 / 交付成果 / 验收标准 ..."
        text text_original "仅上传者可读"
        text text_masked "AI 检索使用"
        vector embedding
    }
    soc_templates {
        string id PK
        bool is_c1
        string report_type "SOC 1 / SOC 2, Type 1 / Type 2"
        string docx_key
    }
    sow_sessions {
        string id PK
        string user_id FK
        string flow "SOC / 其他"
        json fields "已收集的字段"
        text draft
    }
    audit_logs {
        string id PK
        string user_id FK
        string action "上传 / 查看原文 / 下载 / AI 参考"
        string target
        datetime at
    }
```

---

## 6. 合同上传与检索

### 6.1 上传流程

```mermaid
sequenceDiagram
    actor U as 用户
    participant W as 前端
    participant A as API 服务
    participant DB as RDS
    participant S as OBS
    participant Q as OCR / 分析任务

    U->>W: 选择项目 Code
    W->>A: 查询 Code 信息
    A->>DB: projects + project_members
    A-->>W: 显示 EIC（及当前账号是否可上传）
    U->>W: 选择文件并上传
    W->>A: POST /api/contracts (code, file)
    A->>DB: can_upload(当前账号, code)?
    alt 不在该 Code 的 EIC/PIC/小秘书中
        A-->>W: 403「当前账号无权向该项目 Code 上传合同，请核对所选 Code。」
    else 允许
        A->>S: 保存原件（加密）
        A->>DB: 新建合同记录 uploaded_by=当前账号
        A->>Q: 提交 OCR 任务
        Q->>Q: OCR → 关键词/Tag/甲乙方 → 条款切分 → 生成脱敏条款
        Q->>DB: 写入识别结果与条款
        A-->>W: 返回任务进度
    end
```

### 6.2 他人合同可见字段（沿用小秘书端）

| 可见 | 不可见 |
|---|---|
| 项目名称、上传者ID、Engagement Name、甲方、乙方、签约时间 | 合同原文、原件下载、定位到识别全文 |
| 原始关键词、服务领域、具体服务、系统、PIC、EIC | Engagement Code / Description、来源文件、FIC、金额 |
| 「全文命中」：只显示命中了哪些搜索词，不显示句子 | |

检索结果可按 PIC、EIC、上传人、签约时间筛选，勾选后导出 Excel（与 v2.15.0 一致）。

---

## 7. AI 对话式 SOW 生成

```mermaid
flowchart TD
    START["用户输入公司名称 / 业务关键词 / 客户需求"] --> ROUTE["分流：查项目池与历史合同<br/>确认是否 C1、服务类型"]
    ROUTE -->|信息不足| ASK0["AI 追问"] --> ROUTE
    ROUTE -->|SOC 合同| SOC1
    ROUTE -->|其他合同| OTH1

    subgraph SOCFLOW["SOC 合同：固定模板"]
        SOC1["按 C1/非C1 + 报告类型选择模板"] --> SOC2["对话收集字段<br/>公司名称、产品名称、SOC 报告类型、适用标准<br/>报告期间、报告语言、子服务机构（纳入法/剔除法）"]
        SOC2 --> SOC3{"字段齐全且校验通过？"}
        SOC3 -->|否| SOC2
        SOC3 -->|是| SOC4["程序把字段填入 Word 模板<br/>按条件切换条款（AI 不改写正文）"]
    end

    subgraph OTHFLOW["其他合同：参考历史 + 公开资料"]
        OTH1["检索历史合同（脱敏条款）<br/>先同一客户，再同类服务"]
        OTH2["联网检索公开资料<br/>官网、年报、招股书（只发公开查询词）"]
        OTH3["对话确认<br/>服务范围、涉及系统、交付要求、验收口径"]
        OTH1 & OTH2 & OTH3 --> OTH4["大模型起草 SOW<br/>测试范围、测试指标、交付成果、验收标准"]
        OTH4 --> OTH5["防泄露检查<br/>与检索到的条款比对，连续相同过长则改写或删除"]
        OTH5 --> OTH6["每条内容标注来源<br/>未确定的内容标【待确认】"]
    end

    SOC4 --> OUT["SOW 草稿（Word）<br/>需法务 / 项目负责人审核后使用"]
    OTH6 --> OUT
```

### 7.1 SOC 字段校验

| 字段 | 收集方式 | 校验 |
|---|---|---|
| 公司名称、产品名称 | 填写 | 必填 |
| SOC 报告类型 | 选择（如 SOC 1 Type 2） | 必填 |
| 适用标准 | 从已确认选项中选择 | 选项随报告类型变化 |
| 报告期间 | Type 2 填起止日期 | Type 1 只填基准日 |
| 报告语言 | 选择 | 必填 |
| 子服务机构 | 先确认是否涉及 | 涉及时机构名称、纳入法/剔除法必填 |

### 7.2 为什么用检索（RAG）而不是训练模型

- **权限**：训练会把所有合同写进模型参数，无法再按用户控制；检索每次只取允许的内容。
- **时效**：新合同上传后立即可被参考，无需重新训练。
- **可追溯**：每条建议能标注来源类型，便于审核。

---

## 8. 防止他人原文泄露

| 关卡 | 做法 |
|---|---|
| 1. 入库脱敏 | 条款保存两份：原文版（仅上传者）、脱敏版（AI 用）。替换客户名称、人名、金额、具体日期、合同编号 |
| 2. 生成后比对 | 与本次检索到的条款比对，连续相同约 15 字以上要求改写，仍超标则删除；出现在 5 个以上不同客户合同中的短语视为通用法律用语，不计入 |
| 3. 拒绝定向提取 | 系统提示禁止复述 / 引用某一份具体合同；检索接口不接受指定合同 ID |
| 4. 依据只给统计 | 只显示「参考了该客户历史合同 N 份、同类项目 M 份」，不列合同名称、不可点击 |

> 待权衡：同类参考只有 1 份时，即使改写措辞，内容仍接近原合同。可选择接受，或设下限（少于 3 份只给方向性建议）。

---

## 9. 华为云部署

| 组件 | 用途 |
|---|---|
| ELB + WAF | HTTPS 入口、访问控制 |
| ECS / CCE | Web 前端、API 服务、OCR 与分析任务 |
| RDS | 用户、项目池、权限、合同信息、SOW 会话、审计日志 |
| OBS | 合同原件（服务端加密） |
| 检索库 | 全文检索 + 向量检索（具体产品以华为云当前支持为准） |
| ModelArts Studio（MaaS） | 大模型 API（DeepSeek / Qwen 等），API Key 设 IP 白名单 |
| 联网搜索 API | 公开资料检索，只发送公开查询词 |

**上线前必须**：客户合同上云、交给大模型处理、开启联网检索三项，需经 IT 与风险管理部门批准；确认目标区域可用的模型（数据需留境内时尤其注意）。

---

## 10. 实施阶段

```mermaid
flowchart LR
    P1["阶段 1 平台底座<br/>登录、项目池、Code 上传校验<br/>OCR 上云、合同库替代 Excel 总表<br/>按权限检索"] --> P2["阶段 2 SOC 生成<br/>模板 + 字段收集 + 校验"]
    P2 --> P3["阶段 3 其他合同生成<br/>条款切分与脱敏、检索库<br/>联网检索、AI 起草"]
    P3 --> P4["阶段 4 完善<br/>防泄露检查调优、审计报表"]
```

---

## 11. 待确认事项

- [ ] 同一 Code 的 EIC / PIC / 小秘书之间能否互相查看原文（当前：不能）
- [ ] C1 状态来源：项目池字段，还是对接其他系统
- [ ] 项目池数据如何录入：手工、Excel 导入，还是对接现有系统
- [ ] 登录方式：能否接公司统一登录（SSO）
- [ ] SOC 各版本 Word 模板，以及字段与条款的对应规则
- [ ] AI 参考来源只有 1 份时的处理方式
- [ ] IT / 风险管理对上云、大模型、联网检索的审批

---

## 12. 术语

| 术语 | 含义 |
|---|---|
| Code | 项目编号，项目池的主键 |
| EIC / PIC | 项目负责人角色，登记在项目池中 |
| 小秘书 / 小秘书端 | SOW 使用人员及其使用的检索与 AI 对话界面 |
| C1 | 客户分类，决定 SOC 模板版本 |
| SOW | Statement of Work，工作说明书 |
| 脱敏条款 | 替换了客户名称、人名、金额、日期等信息的条款，只供 AI 检索 |
| RAG | 检索增强生成：先检索相关资料，再交给大模型生成 |
