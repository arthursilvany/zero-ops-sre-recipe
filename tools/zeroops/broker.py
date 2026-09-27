"""The single point through which every Azure invocation passes.

FR-11 and CON-02 require that the core and the wizard reach Azure only
through one choke point restricted to read-only verbs. A choke point is worth
having only if bypassing it fails the build, which is T2.02's static check.
This module is the thing that check points at.

Three decisions shape what follows, and each is a refusal rather than a
convention:

1.  **A command is a list of tokens, never a string.** Accepting a string
    would mean splitting it here, and every quoting bug in that split becomes
    an injection. A caller that has a string has not yet decided where its
    arguments end.

2.  **The allow-list decides, and the write-list only explains.** A verb that
    appears in neither list is refused. If the denial depended on recognising
    a write verb, every verb nobody thought of would be permitted, and the
    list of things nobody thought of is the interesting one. The write-list
    exists so the refusal can say why the verb is wrong rather than only that
    it is unknown.

3.  **Planning and running are separate.** `plan` is pure, so the whole
    decision surface is testable with no Azure, no credentials and no
    network. `invoke` is deliberately thin: everything it could get wrong is
    decided before it is called.

What this module does not do: it does not make the framework read-only. The
read-only guarantee is the RBAC grant enforced by Azure Resource Manager
(SEC-001). This is defence in depth, and a bug here is a bug in a second
layer rather than the failure of the first.
"""

import subprocess


CLI = "az"

# Every verb the core and the wizard may issue, with the reason it is here.
# A total registry: a verb absent from this table is refused, so adding a
# capability requires writing down why.
READ_ONLY_VERBS = (
    ("show", "Read one resource by identifier. No side effect."),
    ("list", "Enumerate resources in a scope. No side effect."),
    ("query", "Resource Graph read, the discovery mechanism ADR-0003 chose."),
    ("version", "Record the CLI version in evidence. Touches no subscription."),
)

# Never consulted to decide, only to explain. See decision 2 above.
WRITE_VERBS = (
    "create",
    "delete",
    "update",
    "set",
    "add",
    "remove",
    "start",
    "stop",
    "restart",
    "deploy",
    "apply",
    "invoke",
    "run",
    "execute",
    "assign",
    "purge",
    "move",
    "scale",
    "import",
    "reset",
    "renew",
    "regenerate",
    "revoke",
    "enable",
    "disable",
)

# A token containing any of these is refused whole. None of them can appear
# in a legitimate resource identifier, and each is how a token stops being a
# token once anything downstream joins the list back into a string.
SHELL_METACHARACTERS = (";", "&", "|", "`", "$(", "\n", "\r", "\0", ">", "<")

# A confirmation flag exists because a command is about to change something.
# Its presence on a read is either a copied line or a mistake, and both are
# worth refusing loudly.
CONFIRMATION_FLAGS = ("--yes", "-y", "--force", "--no-wait")


class BrokerRefusal(Exception):
    """The broker declined to issue a command.

    Distinct from a command that ran and failed. A caller that cannot tell
    the two apart would report an Azure error for a request that never left
    the machine.
    """


def allowed_verbs():
    return tuple(verb for verb, _reason in READ_ONLY_VERBS)


def reason_for(verb):
    for name, reason in READ_ONLY_VERBS:
        if name == verb:
            return reason
    return None


def verb_of(command):
    """The last word before the first option.

    `az resource list --subscription x` is a verb of `list` under the group
    `resource`. Reading the first token instead would make every command's
    verb `az`, and reading the last would make it whatever value the caller
    passed.

    Returns None when the command carries no verb at all, which is a refusal
    rather than a default: guessing here would let `az` alone through.
    """
    words = []
    for token in command[1:]:
        if token.startswith("-"):
            break
        words.append(token)
    return words[-1] if words else None


def _reject_token_shapes(command):
    for index, token in enumerate(command):
        if not isinstance(token, str):
            raise BrokerRefusal(
                "token %d is %s, not a string. A command is a list of tokens; "
                "anything else has to be converted, and the conversion is where "
                "quoting goes wrong." % (index, type(token).__name__)
            )
        if not token:
            raise BrokerRefusal(
                "token %d is empty. An empty argument is never meaningful here "
                "and usually means a value was interpolated that did not exist."
                % index
            )
        for bad in SHELL_METACHARACTERS:
            if bad in token:
                raise BrokerRefusal(
                    "token %d contains %r. No resource identifier contains it, "
                    "and it is how a token stops being one token." % (index, bad)
                )


def plan(command, output="json"):
    """Return the argument list to run, or refuse and say why.

    Pure. Every decision the broker makes happens here, so the decision
    surface is testable without Azure, credentials or a network.
    """
    if isinstance(command, str):
        raise BrokerRefusal(
            "a command must be a list of tokens, not a string. Splitting a "
            "string here would put the quoting rules of some other shell "
            "inside this process."
        )
    command = list(command)
    if not command:
        raise BrokerRefusal("an empty command cannot be read-only or otherwise.")

    _reject_token_shapes(command)

    if command[0] != CLI:
        raise BrokerRefusal(
            "command starts with %r rather than %r. Every Azure invocation goes "
            "through this broker (CON-02), so a different program means the "
            "call site is reaching past it." % (command[0], CLI)
        )

    for flag in CONFIRMATION_FLAGS:
        if flag in command:
            raise BrokerRefusal(
                "command carries %s. A confirmation flag exists because "
                "something is about to change; on a read it is a copied line "
                "or a mistake." % flag
            )

    verb = verb_of(command)
    if verb is None:
        raise BrokerRefusal(
            "command names no verb. Allowed verbs are: %s."
            % ", ".join(allowed_verbs())
        )

    if verb not in allowed_verbs():
        if verb in WRITE_VERBS:
            raise BrokerRefusal(
                "verb %r changes state and the core is read-only in v1 "
                "(CON-02). Allowed verbs are: %s." % (verb, ", ".join(allowed_verbs()))
            )
        raise BrokerRefusal(
            "verb %r is not on the read-only allow-list. Allowed verbs are: %s. "
            "Add it to READ_ONLY_VERBS with a reason if it is genuinely a read."
            % (verb, ", ".join(allowed_verbs()))
        )

    planned = list(command)
    if not _names_output(planned):
        # Evidence is compared across runs and across platforms, so the output
        # format cannot depend on a caller's configuration file.
        planned += ["--output", output]
    if "--only-show-errors" not in planned:
        # Upgrade notices and deprecation warnings land on stderr and end up
        # inside captured evidence, where they read as failures.
        planned += ["--only-show-errors"]
    return planned


def _names_output(command):
    return "--output" in command or "-o" in command


def invoke(command, runner=None, output="json"):
    """Plan the command, then run it. Nothing is decided here.

    `runner` exists so the suite can exercise this without Azure. It defaults
    to subprocess.run with shell=False, which is the property that makes the
    token list above worth enforcing.
    """
    planned = plan(command, output=output)
    runner = runner or _default_runner
    return runner(planned)


def _default_runner(planned):
    return subprocess.run(planned, capture_output=True, text=True, shell=False)
