/** Pi hooks extension: run command hooks from `hooks.json` in Pi's agent directory. */

import { type ExtensionAPI, getAgentDir } from "@earendil-works/pi-coding-agent"
import { registerHooks } from "./extension.ts"

export default function (pi: ExtensionAPI): void {
  registerHooks(pi, { agentDir: getAgentDir })
}
