from typing import List

import pytest
from lsprotocol.types import (
    CompletionContext,
    CompletionTriggerKind,
)
from pytest_mock import MockerFixture

from galaxyls.services.completion import XmlCompletionService
from galaxyls.services.context import XmlContextService
from galaxyls.services.definitions import DocumentDefinitionsProvider
from galaxyls.services.tools.macros import MacroDefinitionsProvider
from galaxyls.services.xsd.service import GalaxyToolXsdService
from galaxyls.services.xsd.types import XsdTree
from galaxyls.tests.unit.utils import TestUtils


@pytest.fixture()
def galaxy_xsd_tree() -> XsdTree:
    xsd_service = GalaxyToolXsdService()
    tree = xsd_service.xsd_parser.get_tree()
    return tree


class TestIntegrationXmlCompletionServiceClass:
    @pytest.mark.parametrize(
        "source_with_mark, expected_item_names",
        [
            (
                """
                <tool id="tool" name="tool">
                    <macros>
                        <xml name="macro_1">
                            <param name="input1" />
                        </xml>
                    </macros>
                    <inputs>
                        <expand macro="^"/>
                    </inputs>
                </tool>
                """,
                ["macro_1"],
            ),
            (
                """
                <tool id="tool" name="tool">
                    <macros>
                        <xml name="macro_1"><param name="input1"/></xml>
                        <macro name="macro_2"><param name="input2"/></macro>
                    </macros>
                    <inputs>
                        <expand macro="^"/>
                    </inputs>
                </tool>
                """,
                ["macro_1", "macro_2"],
            ),
            (
                """
                <tool id="tool" name="tool">
                    <macros>
                        <xml name="color_input" token_varname="myvar" token_default_color="#00ff00" token_label="Pick a color">
                            <param name="@VARNAME@" type="color" label="@LABEL@" value="@DEFAULT_COLOR@" />
                        </xml>
                    </macros>
                    <inputs>
                        <expand macro="color_input" ^/>
                    </inputs>
                </tool>
                """,
                ["varname", "default_color", "label"],
            ),
        ],
    )
    def test_completion_on_macro_attribute_returns_expected(
        self,
        galaxy_xsd_tree: XsdTree,
        source_with_mark: str,
        expected_item_names: List[str],
        mocker: MockerFixture,
    ) -> None:
        position, source_without_mark = TestUtils.extract_mark_from_source("^", source_with_mark)
        document = TestUtils.from_source_to_xml_document(source_without_mark)
        context_service = XmlContextService(galaxy_xsd_tree)
        context = context_service.get_xml_context(document, position)
        fake_completion_context = CompletionContext(trigger_kind=CompletionTriggerKind.Invoked)
        workspace = mocker.Mock()
        definitions_provider = DocumentDefinitionsProvider(MacroDefinitionsProvider(workspace))
        completion_service = XmlCompletionService(galaxy_xsd_tree, definitions_provider)

        completion_result = completion_service.get_completion_at_context(context, fake_completion_context)

        assert completion_result
        assert sorted([item.label for item in completion_result.items]) == sorted(expected_item_names)
