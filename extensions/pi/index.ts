/** Pi hooks extension: run command hooks from the package's `hooks.json` and the one in Pi's agent directory. */

import { type ExtensionAPI, getAgentDir } from "@earendil-works/pi-coding-agent"
import { PLUGIN_DIR, registerHooks } from "./extension.ts"

export default function (pi: ExtensionAPI): void {
  registerHooks(pi, { agentDir: getAgentDir, pluginDir: PLUGIN_DIR })
}
