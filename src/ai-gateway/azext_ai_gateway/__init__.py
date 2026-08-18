# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from azure.cli.core import AzCommandsLoader
from azure.cli.core.commands import CliCommandType

# pylint: disable=unused-import
from azext_ai_gateway._help import helps


class AIGatewayCommandsLoader(AzCommandsLoader):

    def __init__(self, cli_ctx=None):
        custom_command_type = CliCommandType(
            operations_tmpl="azext_ai_gateway.custom#{}"
        )
        super().__init__(
            cli_ctx=cli_ctx,
            custom_command_type=custom_command_type,
        )

    def load_command_table(self, args):
        from azext_ai_gateway.commands import load_command_table

        load_command_table(self, args)
        return self.command_table

    def load_arguments(self, command):
        from azext_ai_gateway._params import load_arguments

        load_arguments(self, command)


COMMAND_LOADER_CLS = AIGatewayCommandsLoader
