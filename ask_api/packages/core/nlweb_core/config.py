# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Basic config services, including loading config from config_llm.yaml, config_embedding.yaml, config_retrieval.yaml,
config_webserver.yaml, config_nlweb.yaml
WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml
from dotenv import load_dotenv

from nlweb_core.provider_map import ProviderMap

if TYPE_CHECKING:
    from nlweb_core.embedding import EmbeddingProvider
    from nlweb_core.llm import GenerativeLLMProvider
    from nlweb_core.retriever import ObjectLookupProvider, RetrievalProvider
    from nlweb_core.scoring import ScoringLLMProvider
    from nlweb_core.site_config.base import SiteConfigLookup

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Dataclasses
# =============================================================================


@dataclass
class EmbeddingConfig:
    """Configuration for a single embedding provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalConfig:
    """Configuration for a single retrieval provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServerConfig:
    host: str = "localhost"
    enable_cors: bool = True
    max_connections: int = 100
    timeout: int = 30


@dataclass
class NLWebConfig:
    sites: list[str]
    json_data_folder: str = "./data/json"
    json_with_embeddings_folder: str = "./data/json_with_embeddings"
    chatbot_instructions: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    tool_selection_enabled: bool = True
    memory_enabled: bool = False
    analyze_query_enabled: bool = False
    decontextualize_enabled: bool = True
    required_info_enabled: bool = True
    aggregation_enabled: bool = False
    who_endpoint_enabled: bool = True
    api_keys: dict[str, str] = field(default_factory=dict)
    who_endpoint: str = "http://localhost:8000/who"


@dataclass
class ConversationStorageConfig:
    type: str
    enabled: bool = True
    api_key: str | None = None
    url: str | None = None
    endpoint: str | None = None
    database_path: str | None = None
    auth_method: str | None = None
    collection_name: str | None = None
    database_name: str | None = None
    container_name: str | None = None
    table_name: str | None = None
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    connection_string: str | None = None
    vector_size: int = 1536
    vector_dimensions: int = 1536
    partition_key: str | None = None
    max_conversations: int | None = None
    ttl_seconds: int | None = None
    vector_type: dict[str, Any] | None = None
    rrf: dict[str, Any] | None = None
    knn: dict[str, Any] | None = None


@dataclass
class ObjectStorageConfig:
    """Configuration for a single object storage provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class SiteConfigStorageConfig:
    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringModelConfig:
    """Configuration for a single scoring model provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerativeModelConfig:
    """Configuration for a single generative model provider."""

    import_path: str
    class_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class RankingConfig:
    scoring_questions: list[str] = field(
        default_factory=lambda: ["Is this item relevant to the query?"]
    )


@dataclass
class StorageBehaviorConfig:
    store_anonymous: bool = True
    max_conversations_per_thread: int = 100
    max_threads_per_user: int = 1000
    retention_days: int = 365
    compute_embeddings: bool = True
    batch_size: int = 100
    enable_search: bool = True
    auto_migrate_on_login: bool = True
    max_migrate_conversations: int = 500


# =============================================================================
# AppConfig - Main Configuration Dataclass
# =============================================================================


@dataclass
class AppConfig:
    """
    Main application configuration.

    This is a dataclass that holds all configuration values. The loading logic
    is in the separate load_config() function.
    """

    # Directories
    config_directory: str = ""
    base_output_directory: str | None = None

    # Generative Model Providers
    generative_model_providers: dict[str, GenerativeModelConfig] = field(
        default_factory=dict
    )

    # Embedding Configuration
    embedding_providers: dict[str, EmbeddingConfig] = field(default_factory=dict)
    preferred_embedding_provider: str | None = None

    # Retrieval Providers
    retrieval_providers: dict[str, RetrievalConfig] = field(default_factory=dict)

    # Conversation Storage
    conversation_storage: ConversationStorageConfig | None = None
    conversation_storage_behavior: StorageBehaviorConfig | None = None
    conversation_storage_endpoints: dict[str, ConversationStorageConfig] = field(
        default_factory=dict
    )
    conversation_storage_default: str = "qdrant_local"

    # Object Storage Providers
    object_storage_providers: dict[str, ObjectStorageConfig] = field(
        default_factory=dict
    )

    # Site Config Providers
    site_config_providers: dict[str, SiteConfigStorageConfig] = field(
        default_factory=dict
    )

    # Scoring Model Providers
    scoring_model_providers: dict[str, ScoringModelConfig] = field(default_factory=dict)

    # Ranking Configuration (use get_ranking_config() to access)
    _ranking: RankingConfig | None = None

    # NLWeb Configuration
    nlweb: NLWebConfig | None = None

    # Server Configuration
    server: ServerConfig | None = None
    port: int = 8080
    mode: str = "production"
    nlweb_gateway: str = "nlwm.azurewebsites.net"
    test_user: str = "anonymous"

    # OAuth Configuration
    oauth_providers: dict[str, Any] = field(default_factory=dict)
    oauth_session_secret: str | None = None
    oauth_token_expiration: int = 86400
    oauth_require_auth: bool = False
    oauth_anonymous_endpoints: list[str] = field(default_factory=list)

    # Query methods
    def is_development_mode(self) -> bool:
        """Returns True if the system is running in development mode."""
        return self.mode.lower() == "development"

    def is_testing_mode(self) -> bool:
        """Returns True if the system is running in testing mode."""
        return self.mode.lower() == "testing"

    def should_raise_exceptions(self) -> bool:
        """Returns True if exceptions should be raised instead of caught."""
        return self.is_testing_mode() or self.is_development_mode()

    def get_embedding_config(
        self, provider_name: str | None = None
    ) -> EmbeddingConfig | None:
        """Get the specified embedding provider config or the preferred one if not specified."""
        if provider_name and provider_name in self.embedding_providers:
            return self.embedding_providers[provider_name]
        if (
            self.preferred_embedding_provider
            and self.preferred_embedding_provider in self.embedding_providers
        ):
            return self.embedding_providers[self.preferred_embedding_provider]
        return None

    # Provider instance accessors (delegate to module-level ProviderMaps)

    def get_embedding_provider(self, name: str) -> EmbeddingProvider:
        """Get a cached embedding provider instance by name."""
        if _embedding_provider_map is None:
            raise RuntimeError(
                "Providers not initialized. Call initialize_providers() first."
            )
        return _embedding_provider_map.get(name)

    def get_generative_provider(self, name: str) -> GenerativeLLMProvider:
        """Get a cached generative LLM provider instance by name."""
        if _generative_provider_map is None:
            raise RuntimeError(
                "Providers not initialized. Call initialize_providers() first."
            )
        return _generative_provider_map.get(name)

    def get_scoring_provider(self, name: str) -> ScoringLLMProvider:
        """Get a cached scoring LLM provider instance by name."""
        if _scoring_provider_map is None:
            raise RuntimeError(
                "Providers not initialized. Call initialize_providers() first."
            )
        return _scoring_provider_map.get(name)

    def get_site_config_lookup(self, name: str) -> SiteConfigLookup:
        """Get a cached site config lookup instance by name."""
        if _site_config_provider_map is None:
            raise RuntimeError(
                "Providers not initialized. Call initialize_providers() first."
            )
        return _site_config_provider_map.get(name)

    def get_object_lookup_provider(self, name: str) -> ObjectLookupProvider:
        """Get a cached object lookup provider instance by name."""
        if _object_storage_provider_map is None:
            raise RuntimeError(
                "Providers not initialized. Call initialize_providers() first."
            )
        return _object_storage_provider_map.get(name)

    def get_retrieval_provider(self, name: str) -> RetrievalProvider:
        """Get a cached retrieval provider instance by name."""
        if _retrieval_provider_map is None:
            raise RuntimeError(
                "Providers not initialized. Call initialize_providers() first."
            )
        return _retrieval_provider_map.get(name)

    def get_ranking_config(self) -> RankingConfig:
        """Get ranking config, checking for per-request override first."""
        try:
            return _ranking_config_override.get()
        except LookupError:
            return self._ranking or RankingConfig()


# =============================================================================
# Module-Level Helper Functions
# =============================================================================


def _get_config_directory() -> str:
    """
    Get the configuration directory from environment variable or use default.
    Default is the config folder at the same level as config.py.
    """
    config_dir = os.getenv("NLWEB_CONFIG_DIR")
    if config_dir:
        config_dir = os.path.expanduser(os.path.expandvars(config_dir))
        if not os.path.exists(config_dir):
            print(
                f"Warning: Configured config directory {config_dir} does not exist. Using default."
            )
            config_dir = None

    if not config_dir:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(current_dir, "config")

    return os.path.abspath(config_dir)


def _get_base_output_directory() -> str | None:
    """
    Get the base directory for all output files from the environment variable.
    Returns None if the environment variable is not set.
    """
    base_dir = os.getenv("NLWEB_OUTPUT_DIR")
    if base_dir and not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
            print(f"Created output directory: {base_dir}")
        except Exception as e:
            print(f"Warning: Failed to create output directory {base_dir}: {e}")
            return None
    return base_dir


def _resolve_path(
    path: str, config_directory: str, base_output_directory: str | None
) -> str:
    """
    Resolves a path, considering the base output directory if set.
    """
    if os.path.isabs(path):
        return path

    if base_output_directory:
        return os.path.abspath(os.path.join(base_output_directory, path))
    else:
        return os.path.abspath(os.path.join(config_directory, path))


def _get_config_value(value: Any, default: Any = None) -> Any:
    """
    Get configuration value. If value is an env var name, fetch from environment.
    """
    if value is None:
        return default

    if isinstance(value, str):
        if value.endswith("_ENV") or value.isupper():
            return os.getenv(value, default)
        else:
            return value

    return value


# =============================================================================
# Configuration Loading Functions
# =============================================================================


def _load_embedding_config(
    data: dict,
) -> tuple[dict[str, EmbeddingConfig], str | None]:
    """Load embedding configuration from config dict."""
    if "embedding" not in data:
        return {}, None

    emb_cfg = data["embedding"]
    if not isinstance(emb_cfg, dict):
        raise ValueError("embedding must be a mapping of provider names to configs")

    providers: dict[str, EmbeddingConfig] = {}
    preferred = None
    for provider_name, provider_cfg in emb_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(f"embedding provider '{provider_name}' must be a mapping")
        import_path, class_name = _extract_import_class(
            provider_cfg, "embedding", provider_name
        )
        providers[provider_name] = EmbeddingConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )
        if preferred is None:
            preferred = provider_name
    return providers, preferred


def _load_retrieval_provider_config(data: dict) -> dict[str, RetrievalConfig]:
    """Load retrieval provider configuration from config dict."""
    if "retrieval" not in data:
        return {}

    ret_cfg = data["retrieval"]
    if not isinstance(ret_cfg, dict):
        raise ValueError("retrieval must be a mapping of provider names to configs")

    providers: dict[str, RetrievalConfig] = {}
    for provider_name, provider_cfg in ret_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(f"retrieval provider '{provider_name}' must be a mapping")
        import_path, class_name = _extract_import_class(
            provider_cfg, "retrieval", provider_name
        )
        providers[provider_name] = RetrievalConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_conversation_storage(
    data: dict, config_directory: str, base_output_directory: str | None
) -> ConversationStorageConfig:
    """Load conversation storage configuration from config dict."""
    if "conversation_storage" not in data:
        return ConversationStorageConfig(
            type="qdrant",
            enabled=False,
            database_path=_resolve_path(
                "../data/conversations_db", config_directory, base_output_directory
            ),
            collection_name="nlweb_conversations",
        )

    conv_cfg = data["conversation_storage"]
    return ConversationStorageConfig(
        type=conv_cfg.get("type", "qdrant"),
        enabled=conv_cfg.get("enabled", True),
        connection_string=(
            _get_config_value(conv_cfg.get("connection_string_env"))
            if "connection_string_env" in conv_cfg
            else conv_cfg.get("connection_string")
        ),
        host=conv_cfg.get("account_name"),
        url=(
            _get_config_value(conv_cfg.get("url_env"))
            if "url_env" in conv_cfg
            else conv_cfg.get("url")
        ),
        endpoint=(
            _get_config_value(conv_cfg.get("endpoint_env"))
            if "endpoint_env" in conv_cfg
            else conv_cfg.get("endpoint")
        ),
        api_key=(
            _get_config_value(conv_cfg.get("api_key_env"))
            if "api_key_env" in conv_cfg
            else conv_cfg.get("api_key")
        ),
        auth_method=conv_cfg.get("auth_method", "api_key"),
        table_name=conv_cfg.get("table_name"),
        database_path=(
            _resolve_path(
                conv_cfg["database_path"], config_directory, base_output_directory
            )
            if "database_path" in conv_cfg
            else None
        ),
        collection_name=conv_cfg.get("collection_name"),
        database_name=conv_cfg.get("database_name"),
        container_name=conv_cfg.get("container_name"),
        partition_key=conv_cfg.get("partition_key"),
    )


def _load_object_storage_config(data: dict) -> dict[str, ObjectStorageConfig]:
    """Load object storage provider configuration from config dict."""
    if "object_storage" not in data:
        return {}

    obj_cfg = data["object_storage"]
    if not isinstance(obj_cfg, dict):
        raise ValueError(
            "object_storage must be a mapping of provider names to configs"
        )

    providers: dict[str, ObjectStorageConfig] = {}
    for provider_name, provider_cfg in obj_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"object_storage provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "object_storage", provider_name
        )
        providers[provider_name] = ObjectStorageConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _extract_import_class(
    provider_cfg: dict, config_name: str, provider_name: str
) -> tuple[str, str]:
    """Extract and validate import_path and class_name from provider config."""
    import_path = provider_cfg.get("import_path")
    class_name = provider_cfg.get("class_name")
    if not import_path or not class_name:
        raise ValueError(
            f"{config_name} provider '{provider_name}' must specify import_path and class_name"
        )
    return import_path, class_name


def _build_options(provider_cfg: dict) -> dict[str, Any]:
    """Build options dict from provider config, resolving _env suffixed keys."""
    options: dict[str, Any] = {}
    for key, value in provider_cfg.items():
        if key in ("import_path", "class_name"):
            continue
        if key.endswith("_env"):
            resolved_key = key[:-4]  # Remove _env suffix
            options[resolved_key] = _get_config_value(value)
        else:
            options[key] = value
    return options


def _load_site_config_storage(data: dict) -> dict[str, SiteConfigStorageConfig]:
    """Load site config provider configuration from config dict."""
    if "site_config" not in data:
        return {}

    site_cfg = data["site_config"]
    if not isinstance(site_cfg, dict):
        raise ValueError("site_config must be a mapping of provider names to configs")

    providers: dict[str, SiteConfigStorageConfig] = {}
    for provider_name, provider_cfg in site_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"site_config provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "site_config", provider_name
        )
        providers[provider_name] = SiteConfigStorageConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_scoring_model_config(data: dict) -> dict[str, ScoringModelConfig]:
    """Load scoring model provider configuration from config dict."""
    if "scoring_model" not in data:
        return {}

    scoring_cfg = data["scoring_model"]
    if not isinstance(scoring_cfg, dict):
        raise ValueError("scoring_model must be a mapping of provider names to configs")

    providers: dict[str, ScoringModelConfig] = {}
    for provider_name, provider_cfg in scoring_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"scoring_model provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "scoring_model", provider_name
        )
        providers[provider_name] = ScoringModelConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_generative_model_config(data: dict) -> dict[str, GenerativeModelConfig]:
    """Load generative model provider configuration from config dict."""
    if "generative_model" not in data:
        return {}

    gen_cfg = data["generative_model"]
    if not isinstance(gen_cfg, dict):
        raise ValueError(
            "generative_model must be a mapping of provider names to configs"
        )

    providers: dict[str, GenerativeModelConfig] = {}
    for provider_name, provider_cfg in gen_cfg.items():
        if not isinstance(provider_cfg, dict):
            raise ValueError(
                f"generative_model provider '{provider_name}' must be a mapping"
            )
        import_path, class_name = _extract_import_class(
            provider_cfg, "generative_model", provider_name
        )
        providers[provider_name] = GenerativeModelConfig(
            import_path=import_path,
            class_name=class_name,
            options=_build_options(provider_cfg),
        )

    return providers


def _load_ranking_config(data: dict) -> RankingConfig:
    """Load ranking configuration from config dict."""
    if "ranking_config" not in data:
        return RankingConfig()

    ranking_cfg = data["ranking_config"]
    scoring_questions = ranking_cfg.get(
        "scoring_questions",
        ["Is this item relevant to the query?"],
    )
    return RankingConfig(
        scoring_questions=scoring_questions,
    )


def _load_server_config(data: dict) -> ServerConfig:
    """Load server configuration from config dict."""
    server_cfg = data.get("server", {})

    return ServerConfig(
        host=_get_config_value(server_cfg.get("host"), "localhost"),
        enable_cors=_get_config_value(server_cfg.get("enable_cors"), True),
        max_connections=_get_config_value(server_cfg.get("max_connections"), 100),
        timeout=_get_config_value(server_cfg.get("timeout"), 30),
    )


def _load_nlweb_config(
    data: dict, config_directory: str, base_output_directory: str | None
) -> NLWebConfig:
    """Load NLWeb configuration from config dict."""
    # Parse sites
    sites_str = _get_config_value(data.get("sites"), "")
    sites_list = (
        [site.strip() for site in sites_str.split(",") if site.strip()]
        if sites_str
        else []
    )

    # Data folders
    json_data_folder = "./data/json"
    json_with_embeddings_folder = "./data/json_with_embeddings"

    if "data_folders" in data:
        json_data_folder = _get_config_value(
            data["data_folders"].get("json_data"), json_data_folder
        )
        json_with_embeddings_folder = _get_config_value(
            data["data_folders"].get("json_with_embeddings"),
            json_with_embeddings_folder,
        )

    # Resolve paths
    if base_output_directory:
        if not os.path.isabs(json_data_folder):
            json_data_folder = os.path.join(base_output_directory, "data", "json")
        if not os.path.isabs(json_with_embeddings_folder):
            json_with_embeddings_folder = os.path.join(
                base_output_directory, "data", "json_with_embeddings"
            )

    # Ensure directories exist
    os.makedirs(json_data_folder, exist_ok=True)
    os.makedirs(json_with_embeddings_folder, exist_ok=True)

    # Load API keys
    api_keys = {}
    if "api_keys" in data:
        for key, value in data["api_keys"].items():
            resolved_value = _get_config_value(value)
            api_keys[key] = resolved_value
            logger.info(
                "Loaded API key value: %s", "set" if resolved_value else "not set"
            )

    return NLWebConfig(
        sites=sites_list,
        json_data_folder=json_data_folder,
        json_with_embeddings_folder=json_with_embeddings_folder,
        chatbot_instructions=data.get("chatbot_instructions", {}),
        headers=data.get("headers", {}),
        tool_selection_enabled=_get_config_value(
            data.get("tool_selection_enabled"), True
        ),
        memory_enabled=_get_config_value(data.get("memory_enabled"), False),
        analyze_query_enabled=_get_config_value(
            data.get("analyze_query_enabled"), False
        ),
        decontextualize_enabled=_get_config_value(
            data.get("decontextualize_enabled"), True
        ),
        required_info_enabled=_get_config_value(
            data.get("required_info_enabled"), True
        ),
        aggregation_enabled=_get_config_value(data.get("aggregation_enabled"), False),
        who_endpoint_enabled=_get_config_value(data.get("who_endpoint_enabled"), True),
        api_keys=api_keys,
        who_endpoint=_get_config_value(
            data.get("who_endpoint"), "http://localhost:8000/who"
        ),
    )


def _load_oauth_config(
    data: dict,
) -> tuple[dict[str, Any], str | None, int, bool, list[str]]:
    """Load OAuth configuration from config dict."""
    oauth_providers = {}
    oauth_session_secret = None
    oauth_token_expiration = 86400
    oauth_require_auth = False
    oauth_anonymous_endpoints = []

    # Load providers
    for provider_name, provider_data in data.get("providers", {}).items():
        if provider_data.get("enabled", False):
            client_id = _get_config_value(provider_data.get("client_id_env"))
            client_secret = _get_config_value(provider_data.get("client_secret_env"))

            if client_id and client_secret:
                oauth_providers[provider_name] = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_url": provider_data.get("auth_url"),
                    "token_url": provider_data.get("token_url"),
                    "userinfo_url": provider_data.get("userinfo_url"),
                    "emails_url": provider_data.get("emails_url"),
                    "scope": provider_data.get("scope"),
                }

    # Session config
    session_config = data.get("session", {})
    oauth_session_secret = _get_config_value(session_config.get("secret_key_env"))
    if not oauth_session_secret:
        import secrets

        oauth_session_secret = secrets.token_urlsafe(32)
    oauth_token_expiration = session_config.get("token_expiration", 86400)

    # Auth config
    auth_config = data.get("auth", {})
    oauth_require_auth = auth_config.get("require_auth", False)
    oauth_anonymous_endpoints = auth_config.get("anonymous_endpoints", [])

    return (
        oauth_providers,
        oauth_session_secret,
        oauth_token_expiration,
        oauth_require_auth,
        oauth_anonymous_endpoints,
    )


# =============================================================================
# Main Configuration Loading Function
# =============================================================================


def load_config() -> AppConfig:
    """
    Load configuration from files and return an AppConfig instance.

    This function reads YAML and XML configuration files and constructs
    a fully populated AppConfig dataclass.
    """
    load_dotenv()

    config_directory = _get_config_directory()
    base_output_directory = _get_base_output_directory()

    # Try unified config.yaml first
    unified_config_path = os.path.join(config_directory, "config.yaml")

    if os.path.exists(unified_config_path):
        with open(unified_config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        # Load all configurations from unified file
        generative_model_providers = _load_generative_model_config(data)
        embedding_providers, preferred_embedding_provider = _load_embedding_config(data)
        retrieval_providers = _load_retrieval_provider_config(data)
        conversation_storage = _load_conversation_storage(
            data, config_directory, base_output_directory
        )
        object_storage_providers = _load_object_storage_config(data)
        site_config_providers = _load_site_config_storage(data)
        scoring_model_providers = _load_scoring_model_config(data)
        ranking = _load_ranking_config(data)
        server = _load_server_config(data)
        nlweb = _load_nlweb_config(data, config_directory, base_output_directory)

        # OAuth from separate file or defaults
        oauth_path = os.path.join(config_directory, "config_oauth.yaml")
        if os.path.exists(oauth_path):
            with open(oauth_path, "r") as f:
                oauth_data = yaml.safe_load(f) or {}
            (
                oauth_providers,
                oauth_session_secret,
                oauth_token_expiration,
                oauth_require_auth,
                oauth_anonymous_endpoints,
            ) = _load_oauth_config(oauth_data)
        else:
            (
                oauth_providers,
                oauth_session_secret,
                oauth_token_expiration,
                oauth_require_auth,
                oauth_anonymous_endpoints,
            ) = ({}, None, 86400, False, [])

        return AppConfig(
            config_directory=config_directory,
            base_output_directory=base_output_directory,
            generative_model_providers=generative_model_providers,
            embedding_providers=embedding_providers,
            preferred_embedding_provider=preferred_embedding_provider,
            retrieval_providers=retrieval_providers,
            conversation_storage=conversation_storage,
            conversation_storage_behavior=StorageBehaviorConfig(),
            conversation_storage_endpoints={},
            conversation_storage_default="qdrant_local",
            object_storage_providers=object_storage_providers,
            site_config_providers=site_config_providers,
            scoring_model_providers=scoring_model_providers,
            _ranking=ranking,
            nlweb=nlweb,
            server=server,
            port=data.get("port", 8080),
            mode=data.get("mode", "production"),
            nlweb_gateway=data.get("nlweb_gateway", "nlwm.azurewebsites.net"),
            test_user=os.getenv("TEST_USER", "anonymous"),
            oauth_providers=oauth_providers,
            oauth_session_secret=oauth_session_secret,
            oauth_token_expiration=oauth_token_expiration,
            oauth_require_auth=oauth_require_auth,
            oauth_anonymous_endpoints=oauth_anonymous_endpoints,
        )

    # No config file - return defaults
    return AppConfig(
        config_directory=config_directory,
        base_output_directory=base_output_directory,
        nlweb=NLWebConfig(sites=[]),
        server=ServerConfig(),
        conversation_storage=ConversationStorageConfig(type="qdrant", enabled=False),
        site_config_providers={},
        _ranking=RankingConfig(),
        conversation_storage_behavior=StorageBehaviorConfig(),
    )


# =============================================================================
# Contextvar Infrastructure
# =============================================================================

# Module-private static config - None until initialize_config() is called
_STATIC_CONFIG: AppConfig | None = None

# Per-request ranking config override (no default - falls back to static config)
_ranking_config_override: ContextVar[RankingConfig] = ContextVar(
    "ranking_config_override"
)


def initialize_config() -> AppConfig:
    """
    Initialize the static configuration from files.

    This should be called once at server startup. After this, CONFIG
    can be used to access configuration values.
    """
    global _STATIC_CONFIG
    _STATIC_CONFIG = load_config()
    return _STATIC_CONFIG


def get_config() -> AppConfig:
    """
    Get the application configuration.

    Returns the static config loaded at server startup. For per-request
    overrides of ranking config, use get_config().get_ranking_config()
    which checks the ranking override contextvar.
    """
    if _STATIC_CONFIG is None:
        raise RuntimeError(
            "Configuration not initialized. Call initialize_config() at server startup."
        )
    return _STATIC_CONFIG


@contextmanager
def override_ranking_config(ranking_config: RankingConfig):
    """Temporarily override ranking config for the current context."""
    token = _ranking_config_override.set(ranking_config)
    try:
        yield
    finally:
        _ranking_config_override.reset(token)


# =============================================================================
# Provider Maps (module-level, initialized by initialize_providers() at startup)
# =============================================================================

_embedding_provider_map: ProviderMap | None = None
_generative_provider_map: ProviderMap | None = None
_scoring_provider_map: ProviderMap | None = None
_site_config_provider_map: ProviderMap | None = None
_object_storage_provider_map: ProviderMap | None = None
_retrieval_provider_map: ProviderMap | None = None


@contextmanager
def override_embedding_provider(old_name: str, new_name: str):
    """Temporarily remap an embedding provider name."""
    if _embedding_provider_map is None:
        raise RuntimeError(
            "Providers not initialized. Call initialize_providers() first."
        )
    with _embedding_provider_map.override(old_name, new_name):
        yield


@contextmanager
def override_generative_provider(old_name: str, new_name: str):
    """Temporarily remap a generative provider name."""
    if _generative_provider_map is None:
        raise RuntimeError(
            "Providers not initialized. Call initialize_providers() first."
        )
    with _generative_provider_map.override(old_name, new_name):
        yield


@contextmanager
def override_scoring_provider(old_name: str, new_name: str):
    """Temporarily remap a scoring provider name."""
    if _scoring_provider_map is None:
        raise RuntimeError(
            "Providers not initialized. Call initialize_providers() first."
        )
    with _scoring_provider_map.override(old_name, new_name):
        yield


@contextmanager
def override_site_config_provider(old_name: str, new_name: str):
    """Temporarily remap a site config provider name."""
    if _site_config_provider_map is None:
        raise RuntimeError(
            "Providers not initialized. Call initialize_providers() first."
        )
    with _site_config_provider_map.override(old_name, new_name):
        yield


@contextmanager
def override_object_storage_provider(old_name: str, new_name: str):
    """Temporarily remap an object storage provider name."""
    if _object_storage_provider_map is None:
        raise RuntimeError(
            "Providers not initialized. Call initialize_providers() first."
        )
    with _object_storage_provider_map.override(old_name, new_name):
        yield


@contextmanager
def override_retrieval_provider(old_name: str, new_name: str):
    """Temporarily remap a retrieval provider name."""
    if _retrieval_provider_map is None:
        raise RuntimeError(
            "Providers not initialized. Call initialize_providers() first."
        )
    with _retrieval_provider_map.override(old_name, new_name):
        yield


def initialize_providers(config: AppConfig) -> None:
    """Eagerly create all provider instances from config. Call at server startup."""
    global \
        _embedding_provider_map, \
        _generative_provider_map, \
        _scoring_provider_map, \
        _site_config_provider_map, \
        _object_storage_provider_map, \
        _retrieval_provider_map
    _embedding_provider_map = ProviderMap(
        config=config.embedding_providers,
        error_prefix="Embedding provider",
    )
    _generative_provider_map = ProviderMap(
        config=config.generative_model_providers,
        error_prefix="Generative model provider",
    )
    _scoring_provider_map = ProviderMap(
        config=config.scoring_model_providers,
        error_prefix="Scoring model provider",
    )
    _site_config_provider_map = ProviderMap(
        config=config.site_config_providers,
        error_prefix="Site config provider",
    )
    _object_storage_provider_map = ProviderMap(
        config=config.object_storage_providers,
        error_prefix="Object storage provider",
    )
    _retrieval_provider_map = ProviderMap(
        config=config.retrieval_providers,
        error_prefix="Retrieval provider",
    )


async def close_all_providers() -> None:
    """Close all cached provider instances. Call at server shutdown."""
    if _embedding_provider_map is not None:
        await _embedding_provider_map.close()
    if _generative_provider_map is not None:
        await _generative_provider_map.close()
    if _scoring_provider_map is not None:
        await _scoring_provider_map.close()
    if _site_config_provider_map is not None:
        await _site_config_provider_map.close()
    if _object_storage_provider_map is not None:
        await _object_storage_provider_map.close()
    if _retrieval_provider_map is not None:
        await _retrieval_provider_map.close()
