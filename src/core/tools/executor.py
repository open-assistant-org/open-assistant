"""Tool executor for routing LLM tool calls to service methods."""

import time
from typing import Any, Dict, Optional

from src.core.tools.registry import get_tool_registry
from src.models.nextcloud import UploadFileRequest as NextcloudUploadFileRequest
from src.models.outlook import UploadFileRequest as OutlookUploadFileRequest
from src.utils.logger import get_logger
from src.utils.settings import settings_truthy

logger = get_logger(__name__)

# Import authentication exceptions from integrations
try:
    from src.integrations.outlook.auth import AuthenticationRequiredException as OutlookAuthRequired
except ImportError:
    OutlookAuthRequired = None

try:
    from src.integrations.google.auth import OAuthFlowRequired as GoogleAuthRequired
except ImportError:
    GoogleAuthRequired = None

try:
    from src.integrations.google_ads.auth import (
        GoogleAdsOAuthFlowRequired as GoogleAdsAuthRequired,
    )
except ImportError:
    GoogleAdsAuthRequired = None


class ToolExecutor:
    """Executes tool calls from LLM."""

    def __init__(
        self,
        google_service=None,
        google_ads_service=None,
        outlook_service=None,
        notion_service=None,
        nextcloud_service=None,
        whatsapp_service=None,
        slack_service=None,
        google_news_service=None,
        yahoo_finance_service=None,
        brave_service=None,
        browser_service=None,
        system_service=None,
        search_service=None,
        cron_job_service=None,
        future_task_service=None,
        audit_repo=None,
        conversation_id: Optional[str] = None,
        settings_service=None,
        plugin_service=None,
        mcp_service=None,
    ):
        """
        Initialize tool executor with service instances.

        Args:
            google_service: Google service instance
            outlook_service: Outlook service instance
            notion_service: Notion service instance
            nextcloud_service: Nextcloud service instance
            whatsapp_service: WhatsApp service instance
            google_news_service: Google News service instance
            yahoo_finance_service: Yahoo Finance service instance
            brave_service: Brave Search service instance
            browser_service: Browser service instance
            system_service: System service instance
            search_service: Unified search service instance
            cron_job_service: Cron job service instance
            future_task_service: Future task service instance
            audit_repo: Audit log repository instance
            conversation_id: Conversation ID for audit logging
            settings_service: Settings service instance (for compose_document LLM calls)
            plugin_service: Plugin service instance for dynamic REST API integrations
        """
        self.plugin_service = plugin_service
        self.mcp_service = mcp_service
        self.services = {
            "google": google_service,
            "google_navigator": google_service,  # Same service, different auth (OAuth vs API key)
            "google_ads": google_ads_service,
            "outlook": outlook_service,
            "notion": notion_service,
            "nextcloud": nextcloud_service,
            "whatsapp": whatsapp_service,
            "slack": slack_service,
            "google_news": google_news_service,
            "yahoo_finance": yahoo_finance_service,
            "brave": brave_service,
            "browser": browser_service,
            "system": system_service,
            "search": search_service,
        }
        self.cron_job_service = cron_job_service
        self.future_task_service = future_task_service
        self.settings_service = settings_service
        self.registry = get_tool_registry()
        self.audit_repo = audit_repo
        self.conversation_id = conversation_id

        # Debug logging
        logger.info(
            f"ToolExecutor initialized with audit_repo={audit_repo is not None}, conversation_id={conversation_id}"
        )

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str] = None,
        iteration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments from LLM
            tool_call_id: Tool call ID from LLM (for audit logging)
            iteration: Iteration number in tool calling loop (for audit logging)

        Returns:
            Tool execution result with success status
        """
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")

        # Track execution start time
        start_time = time.time()

        tool = self.registry.get(tool_name)
        if not tool:
            error_result = {"success": False, "error": f"Unknown tool: {tool_name}"}
            execution_time_ms = int((time.time() - start_time) * 1000)
            self._log_tool_execution(
                tool_name=tool_name,
                service_name=None,
                arguments=arguments,
                result=error_result,
                success=False,
                error_message=f"Unknown tool: {tool_name}",
                execution_time_ms=execution_time_ms,
                tool_call_id=tool_call_id,
                iteration=iteration,
            )
            return error_result

        # Route plugin tools directly through PluginService
        if tool.service_name.startswith("plugin_") and self.plugin_service:
            try:
                result = await self.plugin_service.execute_tool(tool_name, arguments)
                execution_time_ms = int((time.time() - start_time) * 1000)
                success_result = {"success": True, "result": result}
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=result,
                    success=True,
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                )
                return success_result
            except Exception as e:
                execution_time_ms = int((time.time() - start_time) * 1000)
                error_msg = str(e)
                error_result = {"success": False, "error": error_msg}
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=error_result,
                    success=False,
                    error_message=error_msg,
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                )
                return error_result

        # Route MCP server tools directly through McpService
        if tool.service_name.startswith("mcp_") and self.mcp_service:
            try:
                result = await self.mcp_service.execute_tool(tool_name, arguments)
                execution_time_ms = int((time.time() - start_time) * 1000)
                success_result = {"success": True, "result": result}
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=result,
                    success=True,
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                )
                return success_result
            except Exception as e:
                execution_time_ms = int((time.time() - start_time) * 1000)
                error_msg = str(e)
                error_result = {"success": False, "error": error_msg}
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=error_result,
                    success=False,
                    error_message=error_msg,
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                )
                return error_result

        service = self.services.get(tool.service_name)
        # "messaging" (notify_owner) is a pseudo-service gated on either WhatsApp
        # or Slack in the registry; it has no service instance because
        # _handle_notify_owner resolves the whatsapp/slack services itself. Let it
        # fall through to _route_tool_call instead of short-circuiting.
        if not service and tool.service_name != "messaging":
            error_result = {
                "success": False,
                "error": f"Service not available: {tool.service_name}",
            }
            execution_time_ms = int((time.time() - start_time) * 1000)
            self._log_tool_execution(
                tool_name=tool_name,
                service_name=tool.service_name,
                arguments=arguments,
                result=error_result,
                success=False,
                error_message=f"Service not available: {tool.service_name}",
                execution_time_ms=execution_time_ms,
                tool_call_id=tool_call_id,
                iteration=iteration,
            )
            return error_result

        try:
            # Route to appropriate service method
            result = await self._route_tool_call(tool_name, service, arguments)
            execution_time_ms = int((time.time() - start_time) * 1000)
            success_result = {"success": True, "result": result}

            self._log_tool_execution(
                tool_name=tool_name,
                service_name=tool.service_name,
                arguments=arguments,
                result=result,
                success=True,
                execution_time_ms=execution_time_ms,
                tool_call_id=tool_call_id,
                iteration=iteration,
            )

            return success_result
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Check if this is an authentication required exception
            if OutlookAuthRequired and isinstance(e, OutlookAuthRequired):
                logger.info("Authentication required for Outlook")
                auth_result = {
                    "success": False,
                    "authentication_required": True,
                    "service": "outlook",
                    "auth_url": e.auth_url,
                    "user_code": e.user_code,
                    "message": str(e),
                }
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=auth_result,
                    success=False,
                    error_message="Authentication required",
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                    authentication_required=True,
                )
                return auth_result

            if GoogleAdsAuthRequired and isinstance(e, GoogleAdsAuthRequired):
                logger.info("Authentication required for Google Ads")
                auth_result = {
                    "success": False,
                    "authentication_required": True,
                    "service": "google_ads",
                    "auth_url": e.auth_url or "",
                    "message": (
                        "Google Ads OAuth authorization required. "
                        "Please visit the Settings page and complete the Google Ads OAuth flow."
                    ),
                }
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=auth_result,
                    success=False,
                    error_message="Authentication required",
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                    authentication_required=True,
                )
                return auth_result

            if GoogleAuthRequired and isinstance(e, GoogleAuthRequired):
                logger.info("Authentication required for Google")
                auth_result = {
                    "success": False,
                    "authentication_required": True,
                    "service": "google",
                    "auth_url": e.auth_url,
                    "message": "Please visit the URL above and authorize the application. Then provide the authorization code.",
                }
                self._log_tool_execution(
                    tool_name=tool_name,
                    service_name=tool.service_name,
                    arguments=arguments,
                    result=auth_result,
                    success=False,
                    error_message="Authentication required",
                    execution_time_ms=execution_time_ms,
                    tool_call_id=tool_call_id,
                    iteration=iteration,
                    authentication_required=True,
                )
                return auth_result

            logger.error(f"Tool execution failed: {e}", exc_info=True)
            error_result = {"success": False, "error": str(e)}
            self._log_tool_execution(
                tool_name=tool_name,
                service_name=tool.service_name,
                arguments=arguments,
                result=error_result,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
                tool_call_id=tool_call_id,
                iteration=iteration,
            )
            return error_result

    async def _route_tool_call(
        self, tool_name: str, service: Any, arguments: Dict[str, Any]
    ) -> Any:
        """
        Route tool call to appropriate service method.

        Args:
            tool_name: Name of the tool
            service: Service instance
            arguments: Tool arguments

        Returns:
            Result from service method

        Raises:
            ValueError: If tool name is unknown
        """
        # Google tools
        if tool_name == "google_send_email":
            return service.send_email(**arguments)
        elif tool_name == "google_read_emails":
            return service.read_emails(**arguments)
        elif tool_name == "google_search_emails":
            return service.search_emails(**arguments)
        elif tool_name == "google_get_email":
            return service.get_email(**arguments)
        elif tool_name == "google_create_draft":
            return service.create_draft(**arguments)
        elif tool_name == "google_reply_email":
            return service.reply_email(**arguments)
        elif tool_name == "google_trash_email":
            return service.trash_email(**arguments)
        elif tool_name == "google_modify_labels":
            return service.modify_labels(**arguments)
        elif tool_name == "google_get_labels":
            return service.get_labels()
        elif tool_name == "google_get_attachment":
            return service.get_attachment(**arguments)
        elif tool_name == "google_list_calendars":
            return service.list_calendars()
        elif tool_name == "google_list_events":
            return service.list_calendar_events(**arguments)
        elif tool_name == "google_get_event":
            return service.get_calendar_event(**arguments)
        elif tool_name == "google_create_event":
            return service.create_calendar_event(**arguments)
        elif tool_name == "google_update_event":
            return service.update_calendar_event(**arguments)
        elif tool_name == "google_delete_event":
            return service.delete_calendar_event(**arguments)

        # Google Drive tools
        elif tool_name == "google_drive_list_files":
            return service.drive_list_files(**arguments)
        elif tool_name == "google_drive_search_files":
            return service.drive_search_files(**arguments)
        elif tool_name == "google_drive_get_file":
            return service.drive_get_file(**arguments)
        elif tool_name == "google_drive_read_file":
            return service.drive_read_file(**arguments)

        # Google Docs tools
        elif tool_name == "google_docs_create":
            return service.docs_create(**arguments)
        elif tool_name == "google_docs_get":
            return service.docs_get(**arguments)
        elif tool_name == "google_docs_append":
            return service.docs_append(**arguments)
        elif tool_name == "google_docs_update":
            return service.docs_update(**arguments)
        elif tool_name == "google_docs_replace_text":
            return service.docs_replace_text(**arguments)

        # Google Sheets tools
        elif tool_name == "google_sheets_create":
            return service.sheets_create(**arguments)
        elif tool_name == "google_sheets_get":
            return service.sheets_get(**arguments)
        elif tool_name == "google_sheets_read":
            return service.sheets_read(**arguments)
        elif tool_name == "google_sheets_write":
            return service.sheets_write(**arguments)
        elif tool_name == "google_sheets_append":
            return service.sheets_append(**arguments)
        elif tool_name == "google_sheets_clear":
            return service.sheets_clear(**arguments)

        # Google Slides tools
        elif tool_name == "google_slides_create":
            return service.slides_create(**arguments)
        elif tool_name == "google_slides_get":
            return service.slides_get(**arguments)
        elif tool_name == "google_slides_add_slide":
            return service.slides_add_slide(**arguments)
        elif tool_name == "google_slides_replace_text":
            return service.slides_replace_text(**arguments)
        elif tool_name == "google_slides_insert_text":
            return service.slides_insert_text(**arguments)

        # Google Places & Routes tools
        elif tool_name == "google_search_places":
            return service.search_places(**arguments)
        elif tool_name == "google_get_place_details":
            return service.get_place_details(**arguments)
        elif tool_name == "google_nearby_places":
            return service.nearby_places(**arguments)
        elif tool_name == "google_get_directions":
            return service.get_directions(**arguments)
        elif tool_name == "google_geocode_place":
            return service.geocode_place(**arguments)
        elif tool_name == "google_reverse_geocode":
            return service.reverse_geocode(**arguments)

        # Google Ads tools
        elif tool_name == "google_ads_get_account_info":
            return service.get_account_info(**arguments)
        elif tool_name == "google_ads_list_campaigns":
            return service.list_campaigns(**arguments)
        elif tool_name == "google_ads_get_campaign":
            return service.get_campaign(**arguments)
        elif tool_name == "google_ads_create_campaign":
            return service.create_campaign(**arguments)
        elif tool_name == "google_ads_update_campaign_status":
            return service.update_campaign_status(**arguments)
        elif tool_name == "google_ads_update_campaign_budget":
            return service.update_campaign_budget(**arguments)
        elif tool_name == "google_ads_list_ad_groups":
            return service.list_ad_groups(**arguments)
        elif tool_name == "google_ads_create_ad_group":
            return service.create_ad_group(**arguments)
        elif tool_name == "google_ads_list_keywords":
            return service.list_keywords(**arguments)
        elif tool_name == "google_ads_add_keyword":
            return service.add_keyword(**arguments)
        elif tool_name == "google_ads_get_campaign_performance":
            return service.get_campaign_performance(**arguments)
        elif tool_name == "google_ads_get_ad_group_performance":
            return service.get_ad_group_performance(**arguments)

        # Outlook tools
        elif tool_name == "outlook_send_email":
            return service.send_email(**arguments)
        elif tool_name == "outlook_create_event":
            return service.create_calendar_event(**arguments)
        elif tool_name == "outlook_read_emails":
            return service.read_emails(**arguments)
        elif tool_name == "outlook_get_email":
            return service.get_email(**arguments)
        elif tool_name == "outlook_search_emails":
            return service.search_emails(**arguments)
        elif tool_name == "outlook_create_draft":
            return service.create_draft(**arguments)
        elif tool_name == "outlook_list_calendars":
            return service.list_calendars()
        elif tool_name == "outlook_list_events":
            return service.list_calendar_events(**arguments)
        elif tool_name == "outlook_update_event":
            return service.update_calendar_event(**arguments)
        elif tool_name == "outlook_delete_event":
            return service.delete_calendar_event(**arguments)
        elif tool_name == "outlook_list_files":
            return service.list_files(**arguments)
        elif tool_name == "outlook_search_files":
            return service.search_files(**arguments)
        elif tool_name == "outlook_read_file":
            return service.read_file(**arguments)
        elif tool_name == "outlook_get_attachment":
            return service.get_attachment(**arguments)
        elif tool_name == "onedrive_upload_file":
            validated = OutlookUploadFileRequest.model_validate(arguments)
            return service.upload_file(**validated.model_dump())
        elif tool_name == "outlook_refresh_credentials":
            return service.refresh_credentials()

        # OneNote tools
        elif tool_name == "onenote_list_notebooks":
            return service.list_notebooks(**arguments)
        elif tool_name == "onenote_get_notebook":
            return service.get_notebook(**arguments)
        elif tool_name == "onenote_list_sections":
            return service.list_sections(**arguments)
        elif tool_name == "onenote_get_section":
            return service.get_section(**arguments)
        elif tool_name == "onenote_list_pages":
            return service.list_pages(**arguments)
        elif tool_name == "onenote_get_page":
            return service.get_page(**arguments)
        elif tool_name == "onenote_create_page":
            return service.create_page(**arguments)
        elif tool_name == "onenote_update_page":
            return service.update_page(**arguments)
        elif tool_name == "onenote_delete_page":
            return service.delete_page(**arguments)
        elif tool_name == "onenote_search":
            return service.search_onenote(**arguments)
        elif tool_name == "onenote_copy_page":
            return service.copy_page(**arguments)
        elif tool_name == "onenote_extract_text":
            return service.extract_page_text(**arguments)
        elif tool_name == "onenote_create_markdown_page":
            return service.create_page_from_markdown(**arguments)
        elif tool_name == "onenote_create_from_template":
            return service.create_page_from_template(**arguments)

        # Microsoft To Do tools
        elif tool_name == "todo_list_task_lists":
            return service.list_todo_lists()
        elif tool_name == "todo_get_task_list":
            return service.get_todo_list(**arguments)
        elif tool_name == "todo_create_task_list":
            return service.create_todo_list(**arguments)
        elif tool_name == "todo_delete_task_list":
            return service.delete_todo_list(**arguments)
        elif tool_name == "todo_list_tasks":
            return service.list_todo_tasks(**arguments)
        elif tool_name == "todo_get_task":
            return service.get_todo_task(**arguments)
        elif tool_name == "todo_create_task":
            return service.create_todo_task(**arguments)
        elif tool_name == "todo_update_task":
            return service.update_todo_task(**arguments)
        elif tool_name == "todo_delete_task":
            return service.delete_todo_task(**arguments)

        # Notion tools
        elif tool_name == "notion_create_note":
            return service.create_note(**arguments)
        elif tool_name == "notion_search":
            return service.search_pages(**arguments)
        elif tool_name == "notion_get_page":
            return service.get_page(**arguments)
        elif tool_name == "notion_get_page_content":
            return service.get_page_content(**arguments)
        elif tool_name == "notion_update_page":
            return service.update_page(**arguments)
        elif tool_name == "notion_append_content":
            return service.append_content(**arguments)
        elif tool_name == "notion_list_databases":
            return service.list_databases()
        elif tool_name == "notion_query_database":
            return service.query_database(**arguments)
        elif tool_name == "notion_delete_page":
            return service.delete_page(**arguments)

        # Nextcloud tools
        elif tool_name == "nextcloud_list_files":
            return service.list_files(**arguments)
        elif tool_name == "nextcloud_search_files":
            return service.search_files(**arguments)
        elif tool_name == "nextcloud_read_file":
            return service.read_file(**arguments)
        elif tool_name == "nextcloud_download_file":
            return service.download_file(**arguments)
        elif tool_name == "nextcloud_upload_file":
            validated = NextcloudUploadFileRequest.model_validate(arguments)
            return service.upload_file(**validated.model_dump())
        elif tool_name == "nextcloud_create_folder":
            return service.create_folder(**arguments)
        elif tool_name == "nextcloud_delete_file":
            return service.delete_file(**arguments)
        elif tool_name == "nextcloud_move_file":
            return service.move_file(**arguments)
        elif tool_name == "nextcloud_copy_file":
            return service.copy_file(**arguments)
        elif tool_name == "nextcloud_get_file_info":
            return service.get_file_info(**arguments)
        elif tool_name == "nextcloud_file_exists":
            return service.file_exists(**arguments)
        elif tool_name == "nextcloud_read_pdf":
            return service.read_pdf(**arguments)

        # WhatsApp tools
        elif tool_name == "whatsapp_send_message":
            return service.send_message(**arguments)
        elif tool_name == "whatsapp_get_status":
            return service.get_status()
        elif tool_name == "whatsapp_configure_webhook":
            return service.configure_webhook(**arguments)

        # Notify owner (WhatsApp or Slack)
        elif tool_name == "notify_owner":
            return self._handle_notify_owner(arguments)

        # Google News tools (no API key required)
        elif tool_name == "google_news_top_headlines":
            return service.google_news_top_headlines()
        elif tool_name == "google_news_search":
            return service.google_news_search(**arguments)
        elif tool_name == "google_news_by_topic":
            return service.google_news_by_topic(**arguments)
        elif tool_name == "google_news_by_location":
            return service.google_news_by_location(**arguments)
        elif tool_name == "google_news_by_site":
            return service.google_news_by_site(**arguments)

        # Yahoo Finance tools (no API key required)
        elif tool_name == "yahoo_finance_get_quote":
            return service.get_quote(**arguments)
        elif tool_name == "yahoo_finance_get_history":
            return service.get_history(**arguments)
        elif tool_name == "yahoo_finance_get_info":
            return service.get_info(**arguments)
        elif tool_name == "yahoo_finance_get_financials":
            return service.get_financials(**arguments)
        elif tool_name == "yahoo_finance_get_news":
            return service.get_news(**arguments)
        elif tool_name == "yahoo_finance_search":
            return service.search(**arguments)

        # Brave Search tools
        elif tool_name == "web_search":
            return service.web_search(**arguments)

        # Browser tools (async)
        elif tool_name == "browse_url":
            return await service.browse_url(**arguments)
        elif tool_name == "browse_get_tree":
            return await service.browse_get_tree(**arguments)
        elif tool_name == "browse_action":
            return await service.browse_action(**arguments)
        elif tool_name == "browse_scroll":
            return await service.browse_scroll(**arguments)
        elif tool_name == "browse_extract":
            return await service.browse_extract()
        elif tool_name == "browse_fetch":
            return await service.browse_fetch(**arguments)

        # System tools
        elif tool_name == "system_fetch_logs":
            return service.fetch_logs(**arguments)
        elif tool_name == "system_get_conversation_text":
            return service.get_conversation_text(**arguments)
        elif tool_name == "system_get_prompt":
            return service.get_prompt(**arguments)
        elif tool_name == "system_update_memory_prompt":
            return service.update_memory_prompt(**arguments)
        elif tool_name == "system_index_memory_facts":
            return service.index_memory_facts(**arguments)
        elif tool_name == "system_update_soul_prompt":
            return service.update_soul_prompt(**arguments)
        elif tool_name == "system_clean_tmp_dir":
            return service.clean_tmp_dir(**arguments)
        elif tool_name == "memory_recall":
            return service.recall_conversation_memory(**arguments)

        # Document tools
        elif tool_name == "compose_document":
            from src.services.document import compose_document

            return await compose_document(**arguments, settings_service=self.settings_service)

        elif tool_name == "analyze_content":
            from src.services.analysis import analyze_content

            return await analyze_content(**arguments, settings_service=self.settings_service)

        elif tool_name == "create_docx":
            from src.services.document import create_docx

            return create_docx(**arguments)

        elif tool_name == "create_pdf":
            from src.services.document import create_pdf

            return create_pdf(**arguments)

        elif tool_name == "create_html":
            from src.services.document import create_html

            return await create_html(**arguments, settings_service=self.settings_service)

        elif tool_name == "search_artifacts":
            return self.services["system"].search_artifacts(**arguments)

        elif tool_name == "store_artifact":
            return self.services["system"].store_artifact(**arguments)

        # Plugin-builder tools
        elif tool_name == "install_plugin":
            if not self.plugin_service:
                return {"status": "error", "message": "Plugin service is not available."}
            return await self.plugin_service.install_from_source(**arguments)

        elif tool_name == "inspect_api_source":
            if not self.plugin_service:
                return {"status": "error", "message": "Plugin service is not available."}
            return await self.plugin_service.inspect_api_source(**arguments)

        elif tool_name == "test_plugin_connection":
            if not self.plugin_service:
                return {"status": "error", "message": "Plugin service is not available."}
            return await self.plugin_service.test_connection(**arguments)

        # Calculator tools
        elif tool_name == "calculate":
            from src.services.calculator import calculate

            return calculate(**arguments)

        # Python execution tool
        elif tool_name == "python_execute":
            from src.services.python_exec import python_execute

            # Honor the same configurable offload threshold as the main loop
            # (llm.tool_output_max_chars) so large stdout is offloaded consistently.
            max_inline_chars = None
            if self.settings_service:
                max_inline_chars = int(
                    self.settings_service.get_config_with_fallback(
                        "llm.tool_output_max_chars", 300000
                    )
                )
            return python_execute(**arguments, max_inline_chars=max_inline_chars)

        # Python autonomous sub-agent
        elif tool_name == "python_agent":
            from src.services.python_agent import python_agent

            return await python_agent(**arguments, settings_service=self.settings_service)

        # Batch tool (iterates any other tool over a list of items)
        elif tool_name == "batch_tool":
            return await self._handle_batch_tool(arguments)

        # Loop tool (runs a pipeline of tools for each item in a list)
        elif tool_name == "loop_tool":
            return await self._handle_loop_tool(arguments)

        # Unified search tools
        elif tool_name == "unified_search":
            return service.search(**arguments)
        elif tool_name == "reindex_search":
            return service.reindex(**arguments)

        # Cron job tools
        elif tool_name == "create_cron_job":
            return self._handle_create_cron_job(arguments)
        elif tool_name == "list_cron_jobs":
            return self._handle_list_cron_jobs(arguments)
        elif tool_name == "get_cron_job":
            return self._handle_get_cron_job(arguments)
        elif tool_name == "update_cron_job":
            return self._handle_update_cron_job(arguments)
        elif tool_name == "delete_cron_job":
            return self._handle_delete_cron_job(arguments)
        elif tool_name == "toggle_cron_job":
            return self._handle_toggle_cron_job(arguments)

        # Future task tools
        elif tool_name == "schedule_task":
            return self._handle_schedule_task(arguments)
        elif tool_name == "list_future_tasks":
            return self._handle_list_future_tasks(arguments)
        elif tool_name == "get_future_task":
            return self._handle_get_future_task(arguments)
        elif tool_name == "cancel_future_task":
            return self._handle_cancel_future_task(arguments)

        # Adaptive planning tools — normally intercepted by MessageHandler
        # before reaching the executor.  These are pass-through fallbacks.
        elif tool_name == "revise_plan":
            return {"note": "revise_plan is handled by the orchestration layer"}
        elif tool_name == "ask_user":
            return {"note": "ask_user is handled by the orchestration layer"}

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _handle_create_cron_job(self, arguments: Dict[str, Any]) -> Any:
        """Handle create_cron_job tool call."""
        if not self.cron_job_service:
            return {"error": "Cron job service not available"}
        job = self.cron_job_service.create_job(**arguments)
        return {
            "message": f"Created cron job '{job['name']}' (ID: {job['job_id']})",
            "job_id": job["job_id"],
            "name": job["name"],
            "cron_expression": job["cron_expression"],
            "job_type": job["job_type"],
            "enabled": job["enabled"],
        }

    def _handle_list_cron_jobs(self, arguments: Dict[str, Any]) -> Any:
        """Handle list_cron_jobs tool call."""
        if not self.cron_job_service:
            return {"error": "Cron job service not available"}
        enabled_only = arguments.get("enabled_only", False)
        jobs = self.cron_job_service.list_jobs(
            enabled_only=bool(enabled_only) if enabled_only else False
        )
        return {
            "jobs": [
                {
                    "job_id": j["job_id"],
                    "name": j["name"],
                    "cron_expression": j["cron_expression"],
                    "job_type": j["job_type"],
                    "enabled": j["enabled"],
                    "last_run_at": j.get("last_run_at"),
                    "next_run_at": j.get("next_run_at"),
                }
                for j in jobs
            ],
            "total": len(jobs),
        }

    def _handle_get_cron_job(self, arguments: Dict[str, Any]) -> Any:
        """Handle get_cron_job tool call."""
        if not self.cron_job_service:
            return {"error": "Cron job service not available"}
        job = self.cron_job_service.get_job(arguments["job_id"])
        if not job:
            return {"error": f"Job {arguments['job_id']} not found"}
        executions = self.cron_job_service.get_job_executions(arguments["job_id"], limit=5)
        return {"job": job, "recent_executions": executions}

    def _handle_update_cron_job(self, arguments: Dict[str, Any]) -> Any:
        """Handle update_cron_job tool call."""
        if not self.cron_job_service:
            return {"error": "Cron job service not available"}
        job_id = arguments.pop("job_id")
        job = self.cron_job_service.update_job(job_id, arguments)
        if not job:
            return {"error": f"Job {job_id} not found"}
        return {"message": f"Updated cron job '{job['name']}'", "job": job}

    def _handle_delete_cron_job(self, arguments: Dict[str, Any]) -> Any:
        """Handle delete_cron_job tool call."""
        if not self.cron_job_service:
            return {"error": "Cron job service not available"}
        deleted = self.cron_job_service.delete_job(arguments["job_id"])
        if not deleted:
            return {"error": f"Job {arguments['job_id']} not found"}
        return {"message": f"Deleted cron job {arguments['job_id']}"}

    def _handle_toggle_cron_job(self, arguments: Dict[str, Any]) -> Any:
        """Handle toggle_cron_job tool call."""
        if not self.cron_job_service:
            return {"error": "Cron job service not available"}
        new_state = self.cron_job_service.toggle_job(arguments["job_id"], arguments.get("enabled"))
        if new_state is None:
            return {"error": f"Job {arguments['job_id']} not found"}
        state_str = "enabled" if new_state else "disabled"
        return {"message": f"Job {arguments['job_id']} {state_str}", "enabled": new_state}

    def _handle_schedule_task(self, arguments: Dict[str, Any]) -> Any:
        """Handle schedule_task tool call."""
        if not self.future_task_service:
            return {"error": "Future task service not available"}

        # Add conversation_id if available
        if self.conversation_id and "conversation_id" not in arguments:
            arguments["conversation_id"] = self.conversation_id

        try:
            task = self.future_task_service.create_task(**arguments)
            return {
                "message": f"Scheduled task '{task['name']}' for {task['scheduled_time']}",
                "task_id": task["task_id"],
                "name": task["name"],
                "scheduled_time": task["scheduled_time"],
                "job_type": task["job_type"],
                "status": task["status"],
            }
        except ValueError as e:
            return {"error": str(e)}

    def _handle_list_future_tasks(self, arguments: Dict[str, Any]) -> Any:
        """Handle list_future_tasks tool call."""
        if not self.future_task_service:
            return {"error": "Future task service not available"}

        status = arguments.get("status")
        tasks = self.future_task_service.list_tasks(status=status)

        return {
            "tasks": [
                {
                    "task_id": t["task_id"],
                    "name": t["name"],
                    "scheduled_time": t["scheduled_time"],
                    "job_type": t["job_type"],
                    "status": t["status"],
                    "created_at": t.get("created_at"),
                    "completed_at": t.get("completed_at"),
                }
                for t in tasks
            ],
            "total": len(tasks),
        }

    def _handle_get_future_task(self, arguments: Dict[str, Any]) -> Any:
        """Handle get_future_task tool call."""
        if not self.future_task_service:
            return {"error": "Future task service not available"}

        task = self.future_task_service.get_task(arguments["task_id"])
        if not task:
            return {"error": f"Task {arguments['task_id']} not found"}

        # Extract executions
        executions = task.pop("recent_executions", [])

        return {"task": task, "recent_executions": executions}

    def _handle_cancel_future_task(self, arguments: Dict[str, Any]) -> Any:
        """Handle cancel_future_task tool call."""
        if not self.future_task_service:
            return {"error": "Future task service not available"}

        try:
            success = self.future_task_service.cancel_task(arguments["task_id"])
            if not success:
                return {"error": f"Task {arguments['task_id']} not found"}
            return {"message": f"Cancelled task {arguments['task_id']}"}
        except ValueError as e:
            return {"error": str(e)}

    def _handle_notify_owner(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a notification to the owner via WhatsApp or Slack.

        Checks whether the chosen channel is enabled and properly configured
        (phone number for WhatsApp, default channel ID for Slack) before
        attempting delivery, and returns an informative error if not.
        """
        message = arguments.get("message", "")
        channel = arguments.get("channel")

        whatsapp_service = self.services.get("whatsapp")
        slack_service = self.services.get("slack")

        if channel is None:
            # Auto-detect: prefer whatsapp if enabled, otherwise fall back to slack
            wa_on = whatsapp_service and settings_truthy(
                whatsapp_service.settings_repo.get("whatsapp.enabled")
            )
            sl_on = slack_service and settings_truthy(
                slack_service.settings_repo.get("slack.enabled")
            )
            if wa_on:
                channel = "whatsapp"
            elif sl_on:
                channel = "slack"
            else:
                return {
                    "success": False,
                    "error": "Neither WhatsApp nor Slack is enabled. Enable one in settings.",
                }

        if channel == "whatsapp":
            if not whatsapp_service:
                return {
                    "success": False,
                    "error": "WhatsApp service is not available.",
                }
            wa_enabled = whatsapp_service.settings_repo.get("whatsapp.enabled")
            if not wa_enabled:
                return {
                    "success": False,
                    "error": (
                        "WhatsApp integration is not enabled. "
                        "Enable it in settings or use channel='slack'."
                    ),
                }
            phone = whatsapp_service.settings_repo.get("whatsapp.phone_number")
            if not phone:
                return {
                    "success": False,
                    "error": (
                        "Owner WhatsApp phone number is not configured (whatsapp.phone_number). "
                        "Set it in settings or use channel='slack'."
                    ),
                }
            return whatsapp_service.send_message_to_owner(message=message)

        elif channel == "slack":
            if not slack_service:
                return {
                    "success": False,
                    "error": "Slack service is not available.",
                }
            slack_enabled = slack_service.settings_repo.get("slack.enabled")
            if not slack_enabled:
                return {
                    "success": False,
                    "error": (
                        "Slack integration is not enabled. "
                        "Enable it in settings or use channel='whatsapp'."
                    ),
                }
            default_channel = slack_service.settings_repo.get("slack.default_channel")
            if not default_channel:
                return {
                    "success": False,
                    "error": (
                        "Default Slack channel is not configured (slack.default_channel). "
                        "Set it in settings or use channel='whatsapp'."
                    ),
                }
            return slack_service.send_message_to_default_channel(message=message)

        else:
            return {
                "success": False,
                "error": f"Unknown channel '{channel}'. Supported values: 'whatsapp', 'slack'.",
            }

    async def _handle_batch_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool repeatedly for each item in a list.

        This lets the LLM set up an iterative action in a single tool call
        instead of burning one LLM round-trip per item.
        """
        target_tool_name = arguments.get("tool_name")
        items = arguments.get("items", [])

        if not target_tool_name:
            return {"error": "tool_name is required"}
        if not items:
            return {"error": "items list is required and cannot be empty"}
        if target_tool_name == "batch_tool":
            return {"error": "batch_tool cannot call itself"}

        # Validate that the target tool exists
        tool = self.registry.get(target_tool_name)
        if not tool:
            return {"error": f"Unknown tool: {target_tool_name}"}

        results = []
        succeeded = 0
        failed = 0

        for idx, item_args in enumerate(items):
            if not isinstance(item_args, dict):
                results.append(
                    {
                        "success": False,
                        "error": f"Item {idx}: expected dict, got {type(item_args).__name__}",
                    }
                )
                failed += 1
                continue

            result = await self.execute_tool(
                tool_name=target_tool_name,
                arguments=item_args,
                tool_call_id=f"batch_{idx}",
            )
            results.append(result)
            if result.get("success"):
                succeeded += 1
            else:
                failed += 1

        return {
            "tool_name": target_tool_name,
            "total": len(items),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    async def _handle_loop_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a pipeline of tools in sequence for each item in a list.

        This lets the LLM apply multiple ordered steps to every item in a single
        tool call instead of burning one LLM round-trip per step per item.
        If a step fails for an item the remaining steps for that item are skipped,
        but the loop continues with the next item.
        """
        steps_raw = arguments.get("steps", [])
        items = arguments.get("items") or [{}]

        if not steps_raw:
            return {"error": "steps list is required and cannot be empty"}
        if not isinstance(steps_raw, list):
            return {"error": "steps must be a list"}

        # Validate and normalise steps up-front
        steps = []
        for idx, s in enumerate(steps_raw):
            if not isinstance(s, dict):
                return {"error": f"Step {idx}: expected an object, got {type(s).__name__}"}
            tool_name = s.get("tool_name")
            if not tool_name:
                return {"error": f"Step {idx}: tool_name is required"}
            if tool_name in ("batch_tool", "loop_tool"):
                return {"error": f"Step {idx}: {tool_name} cannot be used inside loop_tool"}
            if not self.registry.get(tool_name):
                return {"error": f"Step {idx}: Unknown tool: {tool_name}"}
            steps.append({"tool_name": tool_name, "arguments": s.get("arguments") or {}})

        results = []
        items_succeeded = 0
        items_failed = 0

        for item_idx, item in enumerate(items):
            if not isinstance(item, dict):
                results.append(
                    {
                        "item_index": item_idx,
                        "success": False,
                        "error": f"Item {item_idx}: expected dict, got {type(item).__name__}",
                        "steps": [],
                    }
                )
                items_failed += 1
                continue

            step_results = []
            item_failed = False

            for step_idx, step in enumerate(steps):
                # Item fields take precedence over the step's shared arguments
                merged_args = {**step["arguments"], **item}
                result = await self.execute_tool(
                    tool_name=step["tool_name"],
                    arguments=merged_args,
                    tool_call_id=f"loop_{item_idx}_{step_idx}",
                )
                step_results.append(
                    {
                        "step": step_idx + 1,
                        "tool_name": step["tool_name"],
                        **result,
                    }
                )
                if not result.get("success"):
                    item_failed = True
                    break  # Skip remaining steps for this item on failure

            results.append(
                {
                    "item_index": item_idx,
                    "success": not item_failed,
                    "steps": step_results,
                }
            )
            if item_failed:
                items_failed += 1
            else:
                items_succeeded += 1

        return {
            "total_items": len(items),
            "succeeded": items_succeeded,
            "failed": items_failed,
            "results": results,
        }

    def _log_tool_execution(
        self,
        tool_name: str,
        service_name: Optional[str],
        arguments: Dict[str, Any],
        result: Any,
        success: bool,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        tool_call_id: Optional[str] = None,
        iteration: Optional[int] = None,
        authentication_required: bool = False,
    ) -> None:
        """
        Log tool execution to audit log.

        Args:
            tool_name: Name of the tool executed
            service_name: Service name (google, outlook, etc.)
            arguments: Tool arguments
            result: Tool execution result
            success: Whether execution succeeded
            error_message: Error message if failed
            execution_time_ms: Execution time in milliseconds
            tool_call_id: Tool call ID from LLM
            iteration: Iteration number in tool calling loop
            authentication_required: Whether authentication is required
        """
        logger.info(
            f"_log_tool_execution called: tool={tool_name}, service={service_name}, audit_repo={self.audit_repo is not None}"
        )

        if not self.audit_repo:
            logger.warning(f"Skipping audit log for {tool_name}: audit_repo is None")
            return

        try:
            # Sanitize arguments
            sanitized_args = self._sanitize_arguments(arguments)

            # Create result summary (condensed version)
            result_summary = self._create_result_summary(result)

            # Build details dictionary
            details = {
                "tool_name": tool_name,
                "arguments": sanitized_args,
                "result_summary": result_summary,
            }

            if execution_time_ms is not None:
                details["execution_time_ms"] = execution_time_ms

            if tool_call_id:
                details["tool_call_id"] = tool_call_id

            if iteration is not None:
                details["iteration"] = iteration

            if authentication_required:
                details["authentication_required"] = True

            # Log to audit repository
            self.audit_repo.log_event(
                event_type="tool_execution",
                service_name=service_name,
                action=tool_name,
                conversation_id=self.conversation_id,
                success=success,
                error_message=error_message,
                details=details,
            )
        except Exception as e:
            # Don't let audit logging failures break tool execution
            logger.error(f"Failed to log tool execution to audit: {e}")

    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize tool arguments to remove sensitive information.

        Args:
            arguments: Original tool arguments

        Returns:
            Sanitized arguments
        """
        if not arguments:
            return {}

        # Fields to exclude from audit logs
        sensitive_fields = {
            "password",
            "token",
            "secret",
            "api_key",
            "apikey",
            "authorization",
            "auth",
            "credentials",
            "credential",
            "private_key",
            "privatekey",
            "access_token",
            "refresh_token",
        }

        sanitized = {}
        for key, value in arguments.items():
            # Check if key contains sensitive terms
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_arguments(value)
            elif isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            elif isinstance(value, list):
                # Sanitize list items
                sanitized[key] = [
                    self._sanitize_arguments(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                # For other types, just include type name
                sanitized[key] = f"<{type(value).__name__}>"

        return sanitized

    def _create_result_summary(self, result: Any) -> Any:
        """
        Create a condensed summary of tool execution result.

        Args:
            result: Tool execution result

        Returns:
            Condensed result summary
        """
        if isinstance(result, dict):
            # For dict results, keep only key fields
            summary = {}

            # Common fields to include in summary
            important_fields = {
                "id",
                "message_id",
                "thread_id",
                "event_id",
                "page_id",
                "status",
                "success",
                "count",
                "total",
                "created",
                "updated",
                "error",
                "message",
                "authentication_required",
                "service",
            }

            for key, value in result.items():
                if key in important_fields:
                    summary[key] = value
                elif key == "items" and isinstance(value, list):
                    # For lists, just include count
                    summary["items_count"] = len(value)
                elif isinstance(value, (str, int, float, bool, type(None))):
                    # Include simple values up to a reasonable length
                    if isinstance(value, str) and len(value) > 200:
                        summary[key] = value[:200] + "..."
                    else:
                        summary[key] = value

            return summary if summary else result
        elif isinstance(result, list):
            # For list results, return count and first few items
            return {"count": len(result), "sample": result[:3] if len(result) > 0 else []}
        elif isinstance(result, str) and len(result) > 200:
            # Truncate long strings
            return result[:200] + "..."
        else:
            return result
