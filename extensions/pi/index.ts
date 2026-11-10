/** Pi hooks extension: run command hooks from the package's `hooks.json` and the one in Pi's agent directory. */

import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { type ExtensionAPI, getAgentDir } from "@earendil-works/pi-coding-agent"
import { registerHooks } from "./extension.ts"

// extensions/pi/ -> the repository Pi installed -> its plugin directory.
const PLUGIN_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "plugins", "sentinel")

export default function (pi: ExtensionAPI): void {
  registerHooks(pi, { agentDir: getAgentDir, pluginDir: PLUGIN_DIR })
}
