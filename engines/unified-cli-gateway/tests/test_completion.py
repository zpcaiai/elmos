import unittest
from elmos_cli.completion import generate_bash_completion, generate_zsh_completion, generate_fish_completion

class TestCompletion(unittest.TestCase):
    def test_generate_bash_completion(self):
        completion = generate_bash_completion()
        self.assertIn("_elmos_completion()", completion)
        self.assertIn("polyglot", completion)
        self.assertIn("commercial", completion)
        self.assertIn("complete -F _elmos_completion elmos", completion)

    def test_generate_zsh_completion(self):
        completion = generate_zsh_completion()
        self.assertIn("#compdef elmos", completion)
        self.assertIn("polyglot_cmds=", completion)
        self.assertIn("_describe -t commands 'elmos subcommands' commands", completion)
        self.assertIn("_elmos \"$@\"", completion)

    def test_generate_fish_completion(self):
        completion = generate_fish_completion()
        self.assertIn("# Fish completion for elmos CLI", completion)
        self.assertIn("complete -c elmos -n \"__fish_use_subcommand\" -a \"polyglot\"", completion)
        self.assertIn("complete -c elmos -f", completion)
