// OpenCode V2 项目级事件钩子（EEG 脑电波可视化研究工作台）
// 放在 .opencode/plugins/ 下会被 OpenCode 自动加载，无需改动 opencode.jsonc。
//
// 三件事：
//   1) shell.create.before —— 给所有 shell 注入统一的 Python 环境变量，并给分析/测试命令放宽超时
//   2) tool.execute.before —— 把 shell 命令与 MNE 分析调用写进审计日志（科研可复现）
//   3) permission.evaluate —— 递归删除、git push 等危险命令强制改判为 ask
//
// 说明：这里刻意不 `import { Plugin } from "@opencode/plugin"`，
// V2 读取默认导出的 id 与 setup()，普通对象导出即可，避免依赖模块别名解析。

import { appendFileSync, mkdirSync } from "node:fs"
import { join } from "node:path"

// 运行时再解析：后台服务的 cwd 不一定是项目目录，优先用插件自身的 location
let LOG_DIR = join(process.cwd(), ".opencode", "logs")
let LOG_FILE = join(LOG_DIR, "eeg-audit.log")

function audit(line: string): void {
  try {
    mkdirSync(LOG_DIR, { recursive: true })
    appendFileSync(LOG_FILE, `${new Date().toISOString()}  ${line}\n`, "utf8")
  } catch {
    // 审计失败不能影响工具执行
  }
}

function resolveLogDir(ctx: any): void {
  const dir = ctx?.location?.directory ?? process.cwd()
  LOG_DIR = join(dir, ".opencode", "logs")
  LOG_FILE = join(LOG_DIR, "eeg-audit.log")
}

// 递归删除 / 强推 / 磁盘级破坏性操作
const DANGEROUS =
  /(Remove-Item[^\n]*(-Recurse|-Force))|(rm\s+-[a-z]*r[a-z]*f)|(git\s+push)|(rmdir\s+\/s)|(del\s+\/s)|(Format-Volume)|(Remove-Item\s+-Recurse)/i

export default {
  id: "eeg-workbench",
  async setup(ctx: any) {
    resolveLogDir(ctx)

    // ---- 1) shell 环境 ----
    try {
      await ctx.shell.hook("create.before", (event: any) => {
        // 项目既定约定：UTF-8 输出（pytest 报告、pandas 打印、pyedflib 源码构建都依赖）
        event.env.PYTHONUTF8 = "1"

        // 数据分析 / 测试命令可能跑很久（mne 全量测试 200+ 用例），放宽到 10 分钟
        if (/\b(pytest|python|mne|jupyter)\b/i.test(event.command)) {
          event.timeout = Math.max(event.timeout ?? 0, 600_000)
        }

        audit(`shell  ${event.command.replace(/\s+/g, " ").slice(0, 400)}`)
      })
    } catch (err) {
      console.error("[eeg-workbench] shell hook failed:", err)
    }

    // ---- 2) 工具审计 ----
    try {
      await ctx.tool.hook("execute.before", (event: any) => {
        const tool = String(event?.tool ?? "")
        // shell 已在上面记录；这里补记写操作与 MNE 分析步骤
        if (tool === "write" || tool === "edit" || tool === "patch") {
          const path = event?.input?.path ?? event?.input?.filePath ?? ""
          audit(`edit   ${tool} ${path}`)
        } else if (tool.toLowerCase().includes("mne")) {
          audit(`mne    ${tool} ${JSON.stringify(event?.input ?? {}).slice(0, 400)}`)
        }
      })
    } catch (err) {
      console.error("[eeg-workbench] tool hook failed:", err)
    }

    // ---- 3) 危险命令改判 ask ----
    try {
      await ctx.permission.hook("evaluate", (event: any) => {
        if (event.action !== "shell") return
        const cmd = (event.resources ?? []).join(" ")
        if (DANGEROUS.test(cmd)) {
          event.effect = "ask"
          event.message = `eeg-workbench 钩子：该命令具有破坏性，需人工确认 —— ${cmd.slice(0, 160)}`
        }
      })
    } catch (err) {
      console.error("[eeg-workbench] permission hook failed:", err)
    }

    audit("plugin eeg-workbench loaded")
  },
}
