"""Utilities to validate Galaxy xml tool wrappers.
"""

from typing import List, Optional

from galaxy.util import xml_macros
from lxml import etree
from pygls.lsp.types import Diagnostic, Position, Range
from pygls.workspace import Document

from galaxyls.services.tools.document import GalaxyToolXmlDocument

from ..xml.document import XmlDocument


class GalaxyToolValidationService:
    """Service providing diagnostics for errors in the XML validation."""

    def __init__(self, server_name: str, xsd_schema: etree.XMLSchema):
        """Initializes the validator"""
        self.server_name = server_name
        self.xsd_schema = xsd_schema

    def validate_document(self, xml_document: XmlDocument) -> List[Diagnostic]:
        """Validates the XML document and returns a list of diagnostics
        if there are any problems.

        Args:
            xml_document (XmlDocument): The XML document. Can be a tool wrapper or macro
            definition file.

        Returns:
            List[Diagnostic]: The list of issues found in the document.
        """

        syntax_errors = self._check_syntax(xml_document.document)
        if syntax_errors:
            return syntax_errors

        if not xml_document.is_tool_file:
            return []
        try:
            xml_tree = etree.fromstring(xml_document.document.source)
            return self._validate_tree(xml_tree)
        except ExpandMacrosFoundException:
            result = self._validate_expanded(xml_document)
            return result
        except etree.XMLSyntaxError as e:
            return self._build_diagnostics_from_syntax_error(e)

    def _get_macros_range(self, xml_document: XmlDocument) -> Optional[Range]:
        """Given a XML document and its corresponding ElementTree, finds
        the first macro import element and returns its Range position
        inside the document.

        Args:
            document (Document): The XML tool document.
            xml_tree (etree.ElementTree): The corresponding ElementTree of the document.

        Returns:
            Optional[Range]: The Range position of the import file if it exists.
        """
        tool = GalaxyToolXmlDocument.from_xml_document(xml_document)
        element = tool.get_macros_element()
        if element:
            range = xml_document.get_element_name_range(element)
            return range

    def _check_syntax(self, document: Document) -> List[Diagnostic]:
        """Check if the XML document contains any syntax error and returns it in a list.

        Args:
            document (Document): The XML document.

        Returns:
            List[Diagnostic]: The list containing the syntax error found or an empty list.
        """
        try:
            etree.fromstring(document.source)
            return []
        except etree.XMLSyntaxError as e:
            return self._build_diagnostics_from_syntax_error(e)

    def _validate_expanded(self, xml_document: XmlDocument) -> List[Diagnostic]:
        """Validates the document after loading all the macros referenced and expands them.

        Args:
            document (Document): [description]
            xml_tree (etree.ElementTree): [description]

        Returns:
            List[Diagnostic]: [description]
        """
        error_range = None
        try:
            error_range = self._get_macros_range(xml_document)
            expanded_tool_tree, _ = xml_macros.load_with_references(xml_document.document.path)
            expanded_xml = self._remove_macros(expanded_tool_tree)
            root = expanded_xml.getroot()
            self.xsd_schema.assertValid(root)
            return []
        except etree.DocumentInvalid as e:
            diagnostics = [
                Diagnostic(
                    range=error_range,
                    message=f"Validation error on expanded document (after replacing macros): {error.message}",
                    source=self.server_name,
                )
                for error in e.error_log.filter_from_errors()
            ]
            return diagnostics

        except etree.XMLSyntaxError as e:
            result = Diagnostic(
                range=error_range,
                message=f"Syntax error on imported macros: {e.msg}",
                source=self.server_name,
            )
            return [result]

    def _validate_tree(self, xml_tree: etree._ElementTree) -> List[Diagnostic]:
        """Validates an XML tree against the XSD schema.

        Args:
            xml_tree (etree.ElementTree): The root element

        Returns:
            List[Diagnostic]: The diagnosis results
        """
        try:
            self.xsd_schema.assertValid(xml_tree)
            return []
        except etree.DocumentInvalid as e:
            return self._build_diagnostics(e.error_log, xml_tree)

    def _remove_macros(self, tool_xml: etree._ElementTree) -> etree._ElementTree:
        """Removes the macros section from the tool tree.

        Args:
            tool_xml (etree._ElementTree): The tool element tree.

        Returns:
            etree.ElementTree: The tool element tree without the macros section.
        """
        to_remove = []
        for macros_el in tool_xml.getroot().findall("macros"):
            to_remove.append(macros_el)
        for macros_el in to_remove:
            tool_xml.getroot().remove(macros_el)
        return tool_xml

    def _build_diagnostics(
        self, error_log: etree._ListErrorLog, xml_tree: Optional[etree._ElementTree] = None
    ) -> List[Diagnostic]:
        """Gets a list of diagnostics from the XSD validation error log.

        Args:
            error_log (etree._ListErrorLog): The error log generated after XSD schema validation.
            xml_tree (Optional[etree.ElementTree], optional): The element tree associated with
            the error log. Defaults to None.

        Raises:
            ExpandMacrosFoundException: This is raised when a macro ``expand`` element is found in the error log.
            The ``expand`` element is not part of the XSD so, when this exception is raised, we know that
            the document must expand the macros before validation.

        Returns:
            List[Diagnostic]: The list of resulting diagnostic items found in the error log.
        """
        diagnostics = []
        for error in error_log.filter_from_errors():
            if "expand" in error.message:
                raise ExpandMacrosFoundException(xml_tree)

            result = Diagnostic(
                range=Range(
                    start=Position(line=error.line - 1, character=error.column),
                    end=Position(line=error.line - 1, character=error.column),
                ),
                message=error.message,
                source=self.server_name,
            )
            diagnostics.append(result)
        return diagnostics

    def _build_diagnostics_from_syntax_error(self, error: etree.XMLSyntaxError) -> List[Diagnostic]:
        """Builds a Diagnostic element from a XMLSyntaxError.

        Args:
            error (etree.XMLSyntaxError): The syntax error.

        Returns:
            Diagnostic: The converted Diagnostic item.
        """
        result = Diagnostic(
            range=Range(
                start=Position(line=error.lineno - 1, character=error.position[0] - 1),
                end=Position(line=error.lineno - 1, character=error.position[1] - 1),
            ),
            message=error.msg,
            source=self.server_name,
        )
        return [result]


class ExpandMacrosFoundException(Exception):
    """This exceptions indicates that the current tool contains
    macros and they should be expanded before validation.
    """
