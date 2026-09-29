#!/usr/bin/env bash
set -euo pipefail
CHECK_ONLY="false"; INCLUDE_DOCKER="false"; INCLUDE_NODE="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY="true"; shift ;;
    --include-docker) INCLUDE_DOCKER="true"; shift ;;
    --include-node) INCLUDE_NODE="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
has(){ command -v "$1" >/dev/null 2>&1; }
install_brew(){ [[ "$CHECK_ONLY" == "true" ]] && return; brew install "$@"; }
install_brew_cask(){ [[ "$CHECK_ONLY" == "true" ]] && return; brew install --cask "$@"; }
install_apt(){ [[ "$CHECK_ONLY" == "true" ]] && return; sudo apt-get update && sudo apt-get install -y "$@"; }
ensure_vscode_ext(){ has code || return; code --list-extensions | grep -qx "$1" || [[ "$CHECK_ONLY" == "true" ]] || code --install-extension "$1" --force >/dev/null; }
OS="$(uname -s)"
if [[ "$OS" == "Darwin" ]]; then
  has brew || { echo "Install Homebrew first: https://brew.sh" >&2; exit 1; }
  has git || install_brew git
  has python3.13 || install_brew python@3.13
  has uv || install_brew uv
  has az || install_brew azure-cli
  has azd || install_brew azure-developer-cli
  has pwsh || install_brew powershell
  has code || install_brew_cask visual-studio-code
  [[ "$INCLUDE_DOCKER" == "true" ]] && { has docker || install_brew_cask docker; }
  [[ "$INCLUDE_NODE" == "true" ]] && { has node || install_brew node@22; }
elif [[ "$OS" == "Linux" ]]; then
  has git || install_apt git curl ca-certificates gnupg lsb-release
  has python3 || install_apt python3 python3-venv python3-pip
  has uv || { [[ "$CHECK_ONLY" == "true" ]] || curl -LsSf https://astral.sh/uv/install.sh | sh; }
  has az || echo "Azure CLI missing. Install from https://learn.microsoft.com/cli/azure/install-azure-cli-linux" >&2
  has azd || echo "azd missing. Install from https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd" >&2
  has code || echo "VS Code missing. Install from https://code.visualstudio.com/docs/setup/linux" >&2
  [[ "$INCLUDE_NODE" == "true" ]] && { has node || install_apt nodejs npm; }
else
  echo "Unsupported OS: $OS" >&2; exit 1
fi
if has azd; then
  azd config set auth.useAzCliAuth true >/dev/null || true
  azd ext list 2>/dev/null | grep -q 'azure\.ai\.agents' || [[ "$CHECK_ONLY" == "true" ]] || azd ext install azure.ai.agents
fi
for ext in ms-python.python ms-toolsai.jupyter ms-windows-ai-studio.windows-ai-studio ms-azuretools.vscode-bicep ms-azuretools.vscode-docker; do ensure_vscode_ext "$ext"; done
printf '\n%-24s %s\n' Tool Version
printf '%-24s %s\n' Git "$(git --version 2>/dev/null || echo missing)"
printf '%-24s %s\n' Python "$(python3 --version 2>/dev/null || python --version 2>/dev/null || echo missing)"
printf '%-24s %s\n' uv "$(uv --version 2>/dev/null || echo missing)"
printf '%-24s %s\n' 'Azure CLI' "$(az version --query '"azure-cli"' -o tsv 2>/dev/null || echo missing)"
printf '%-24s %s\n' azd "$(azd version 2>/dev/null | head -n1 || echo missing)"
printf '%-24s %s\n' Docker "$(docker --version 2>/dev/null || echo optional-missing)"
printf '%-24s %s\n' Node "$(node --version 2>/dev/null || echo optional-missing)"
echo "If a newly installed command is missing, restart your terminal."
