# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Query analysis handler that dynamically loads and executes enabled query analysis modules.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from xml.etree import ElementTree as ET
import asyncio
import importlib
import os
import json
import re
from nlweb_core.utils import fill_prompt_variables

# Load query_analysis.xml once at module level
query_analysis_tree = None


def read_xml_file(file_path):
    try:
        return ET.parse(file_path).getroot()
    except Exception as e:
        raise


# Initialize on module load
try:
    # Get the directory where this module is located
    module_dir = os.path.dirname(__file__)
    query_analysis_xml_path = os.path.join(module_dir, "query_analysis.xml")

    query_analysis_tree = read_xml_file(query_analysis_xml_path)

    # Try to load decontextualizer.xml if it exists
    decontextualizer_xml_path = os.path.join(module_dir, "decontextualizer.xml")
    if os.path.exists(decontextualizer_xml_path):
        decontextualizer_tree = read_xml_file(decontextualizer_xml_path)
    else:
        decontextualizer_tree = query_analysis_tree
except Exception as e:
    import traceback

    traceback.print_exc()
    pass


class QueryAnalysisHandler:
    """
    Handler that executes enabled query analysis modules in parallel.

    Each enabled QueryAnalysis node in the XML configuration is dynamically loaded,
    instantiated, and executed asynchronously. Results are stored in the results
    dictionary with the ref attribute as the key.
    """

    def __init__(self, request, site_config: dict):
        """
        Initialize the handler with an empty results dictionary.

        Args:
            request: The AskRequest containing query and context
            site_config: Optional site configuration dict to pass to analysis handlers
        """
        from nlweb_core.protocol.models import AskRequest

        self.results = {}
        self.request: AskRequest = request
        self.site_config = site_config
        self.done = False

    async def do(self):
        """
        Execute all enabled query analysis modules in parallel.

        This method:
        1. Reads the query_analysis.xml tree
        2. Finds all enabled QueryAnalysis nodes
        3. Dynamically imports the class specified in the ref attribute from the module in method field
        4. Creates instances passing self as the handler
        5. Executes their do() methods in parallel
        6. Collects results in self.results dictionary
        """
        global query_analysis_tree

        if query_analysis_tree is None:
            return

        # Create tasks as we iterate through enabled QueryAnalysis nodes
        tasks = []

        for node in query_analysis_tree.findall(".//QueryAnalysis"):
            enabled = node.get("enabled", "false").lower() == "true"
            ref = node.get("ref")

            if enabled and ref:
                try:
                    # Get the method child element
                    method_node = node.find("method")
                    if method_node is None or not method_node.text:
                        self.results[ref] = {"error": "No method element found in XML"}
                        continue

                    module_name = method_node.text.strip()

                    # Special case for defaultQueryAnalysisHandler
                    if module_name == "defaultQueryAnalysisHandler":
                        instance = DefaultQueryAnalysisHandler(
                            self.request, xml_node=node, site_config=self.site_config
                        )
                    else:
                        # For other handlers, import from the specified module
                        full_module_name = f"nlweb_core.query_analysis.{module_name}"
                        class_name = ref

                        module = importlib.import_module(full_module_name)
                        analysis_class = getattr(module, class_name)

                        # Create instance passing self as handler and the XML node
                        instance = analysis_class(self, node)

                    # Create task for async execution
                    task = asyncio.create_task(self._execute_analysis(ref, instance))
                    tasks.append(task)

                except (ImportError, AttributeError) as e:
                    self.results[ref] = {"error": str(e)}

        # Execute all tasks in parallel and update results as they complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Mark as done
        self.done = True
        return self.results

    async def _execute_analysis(self, ref, instance):
        """Execute a single analysis and store the result."""
        try:
            result = await instance.do()
            self.results[ref] = result
        except Exception as e:
            self.results[ref] = {"error": str(e)}


class DefaultQueryAnalysisHandler:
    """
    Default handler for query analysis that extracts prompt and response structure
    from XML, performs variable substitution, and calls the LLM.
    """

    def __init__(
        self,
        request,
        site_config: dict,
        xml_node=None,
        prompt_ref=None,
        root_node=query_analysis_tree,
    ):
        """
        Initialize with request and XML node.

        Args:
            request: The AskRequest containing query and context
            xml_node: The XML QueryAnalysis node with promptString and returnStruc
            prompt_ref: Reference to find the XML node if xml_node is not provided
            root_node: Root XML tree to search for prompt_ref
            site_config: Optional site configuration dict. If provided with an
                'item_type' key, it will be used instead of doing a lookup.
        """
        from nlweb_core.protocol.models import AskRequest

        self.request: AskRequest = request
        self.site_config = site_config
        if prompt_ref is None and xml_node is None:
            raise ValueError(
                "Both prompt_ref and xml_node cannot be None. One must be provided."
            )
        if xml_node is None:
            # Try to find the xml_node from the root_node using prompt_ref
            tree = root_node
            if tree is not None and prompt_ref is not None:
                for node in tree.findall(".//QueryAnalysis"):
                    ref = node.get("ref")
                    if ref == prompt_ref:
                        xml_node = node
                        break
            if xml_node is None:
                raise ValueError("Could not find xml_node for given prompt_ref.")
        self.xml_node = xml_node

    def _build_prompt_params(self) -> dict:
        """Build prompt variable substitution dict from the request object."""
        query = self.request.query
        context = self.request.context

        # Get item_type from site_config if provided, otherwise do lookup
        if self.site_config and "item_type" in self.site_config:
            site_item_type = self.site_config["item_type"]
        else:
            site_item_type = "item"

        params = {
            "request.rawQuery": query.text,
            "request.query": query.text,
            "request.site": query.site,
            "site.itemType": site_item_type,
        }

        # Add context-related params if available
        if context:
            if context.prev:
                params["request.previousQueries"] = ", ".join(context.prev)
            if context.text:
                params["request.context"] = context.text

        return params

    async def do(self):
        """
        Execute the default query analysis:
        1. Extract promptString and returnStruc from XML node
        2. Substitute variables in the prompt
        3. Call ask_llm
        4. Return the result
        """
        # Extract promptString
        prompt_node = self.xml_node.find("promptString")
        if prompt_node is None or not prompt_node.text:
            return {"error": "No promptString found in XML"}

        prompt_str = prompt_node.text.strip()

        # Extract returnStruc
        return_struc_node = self.xml_node.find("returnStruc")
        if return_struc_node is None or not return_struc_node.text:
            return {"error": "No returnStruc found in XML"}

        # Parse the returnStruc JSON
        try:
            return_struc_text = return_struc_node.text.strip()
            return_struc = json.loads(return_struc_text)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in returnStruc: {e}"}

        # Build and substitute variables in the prompt
        prompt_params = self._build_prompt_params()
        filled_prompt = fill_prompt_variables(prompt_str, prompt_params)

        # Call the LLM
        try:
            from nlweb_core.llm import ask_llm

            result = await ask_llm(
                filled_prompt,
                return_struc,
                level="low",
                timeout=8,
                query_params=prompt_params,
            )
            return result
        except Exception as e:
            return {"error": f"LLM call failed: {e}"}
