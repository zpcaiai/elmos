"""Shell autocompletion script generator for ELMOS Enterprise CLI.
"""

from __future__ import annotations


def generate_bash_completion() -> str:
    return """# Bash completion for elmos CLI
_elmos_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="status polyglot commercial assurance foundry billing pipeline config completion interactive"
    local polyglot_cmds="status routes transform formal-check fuzz-matrix certify-route"
    local commercial_cmds="status kernels pipelines"
    local assurance_cmds="status layers"
    local foundry_cmds="status packs pipelines"
    local billing_cmds="plans estimate"
    local config_cmds="show set init"
    local formats="table json yaml markdown html"

    case "${prev}" in
        elmos)
            COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
            return 0
            ;;
        polyglot)
            COMPREPLY=( $(compgen -W "${polyglot_cmds}" -- "${cur}") )
            return 0
            ;;
        commercial)
            COMPREPLY=( $(compgen -W "${commercial_cmds}" -- "${cur}") )
            return 0
            ;;
        assurance)
            COMPREPLY=( $(compgen -W "${assurance_cmds}" -- "${cur}") )
            return 0
            ;;
        foundry)
            COMPREPLY=( $(compgen -W "${foundry_cmds}" -- "${cur}") )
            return 0
            ;;
        billing)
            COMPREPLY=( $(compgen -W "${billing_cmds}" -- "${cur}") )
            return 0
            ;;
        config)
            COMPREPLY=( $(compgen -W "${config_cmds}" -- "${cur}") )
            return 0
            ;;
        --format)
            COMPREPLY=( $(compgen -W "${formats}" -- "${cur}") )
            return 0
            ;;
        --src-lang|--tgt-lang|--source-surface|--target-surface)
            local langs="java csharp python typescript go rust cpp c abap openedge cobol rpg"
            COMPREPLY=( $(compgen -W "${langs}" -- "${cur}") )
            return 0
            ;;
    esac

    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "--format --export-html --json --yaml --help" -- "${cur}") )
        return 0
    fi
}
complete -F _elmos_completion elmos
"""


def generate_zsh_completion() -> str:
    return """#compdef elmos
_elmos() {
    local -a commands polyglot_cmds commercial_cmds assurance_cmds foundry_cmds billing_cmds config_cmds

    commands=(
        'status:Show global system health, engines, and skill inventory'
        'polyglot:Polyglot Semantic Compiler operations'
        'commercial:Commercial Capability Expansion kernels'
        'assurance:Semantic Assurance & formal proof layers'
        'foundry:Knowledge-Skill-Model Foundry ecosystem'
        'billing:Pricing, billing & FinOps metering'
        'pipeline:Execute end-to-end composite cross-engine pipeline'
        'config:Manage local .elmosrc.yaml configuration'
        'completion:Generate shell autocompletion scripts'
        'interactive:Launch interactive REPL modernizer wizard'
    )

    _arguments -C \
        '--format[Output format]:format:(table json yaml markdown html)' \
        '--export-html[Export executive HTML report]:file:_files' \
        '--json[Quick JSON output]' \
        '--yaml[Quick YAML output]' \
        '1: :->command' \
        '*:: :->args'

    case $state in
        command)
            _describe -t commands 'elmos subcommands' commands
            ;;
        args)
            case $words[1] in
                polyglot)
                    polyglot_cmds=('status:Show compiler status' 'routes:List 784 routes' 'transform:Transform code' 'formal-check:SMT solver check' 'fuzz-matrix:Run fuzzing' 'certify-route:Certify route')
                    _describe -t polyglot_cmds 'polyglot actions' polyglot_cmds
                    ;;
                commercial)
                    commercial_cmds=('status:Commercial status' 'kernels:List K1-K8 kernels' 'pipelines:List commercial pipelines')
                    _describe -t commercial_cmds 'commercial actions' commercial_cmds
                    ;;
                foundry)
                    foundry_cmds=('status:Foundry status' 'packs:List 41 packs' 'pipelines:List 14 pipelines')
                    _describe -t foundry_cmds 'foundry actions' foundry_cmds
                    ;;
                billing)
                    billing_cmds=('plans:List pricing plans' 'estimate:Estimate workload FinOps cost')
                    _describe -t billing_cmds 'billing actions' billing_cmds
                    ;;
            esac
            ;;
    esac
}
_elmos "$@"
"""


def generate_fish_completion() -> str:
    return """# Fish completion for elmos CLI
complete -c elmos -f
complete -c elmos -n "__fish_use_subcommand" -a "status" -d "Show global system health and skill inventory"
complete -c elmos -n "__fish_use_subcommand" -a "polyglot" -d "Polyglot Semantic Compiler operations"
complete -c elmos -n "__fish_use_subcommand" -a "commercial" -d "Commercial Capability Expansion kernels"
complete -c elmos -n "__fish_use_subcommand" -a "assurance" -d "Semantic Assurance & formal proof layers"
complete -c elmos -n "__fish_use_subcommand" -a "foundry" -d "Knowledge-Skill-Model Foundry ecosystem"
complete -c elmos -n "__fish_use_subcommand" -a "billing" -d "Pricing, billing & FinOps metering"
complete -c elmos -n "__fish_use_subcommand" -a "pipeline" -d "Execute end-to-end composite cross-engine pipeline"
complete -c elmos -n "__fish_use_subcommand" -a "interactive" -d "Launch interactive REPL modernizer wizard"
complete -c elmos -n "__fish_use_subcommand" -a "completion" -d "Generate shell completion scripts"
complete -c elmos -n "__fish_use_subcommand" -a "config" -d "Manage .elmosrc.yaml configuration"
"""
