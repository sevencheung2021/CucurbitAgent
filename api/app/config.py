from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
# Scientific data lives under cuagent-platform/data/science/ (see data/README.md).
_DEFAULT_SCIENCE = BASE_DIR / "data" / "science"
DATA_ROOT = Path(os.getenv("CUAGENT_DATA_ROOT", str(_DEFAULT_SCIENCE)))
_RUNTIME = BASE_DIR / "data" / "runtime"
_GENES = DATA_ROOT / "genes"


class Settings:
    content_dir: Path = Path(os.getenv("CUAGENT_CONTENT_DIR", BASE_DIR / "content"))
    visit_db_path: Path = Path(os.getenv("CUAGENT_VISIT_DB", _RUNTIME / "visit_analytics.db"))
    feedback_db_path: Path = Path(os.getenv("CUAGENT_FEEDBACK_DB", _RUNTIME / "feedback.db"))
    auth_db_path: Path = Path(os.getenv("CUAGENT_AUTH_DB", _RUNTIME / "auth.db"))
    analytics_db_path: Path = Path(os.getenv("CUAGENT_ANALYTICS_DB", _RUNTIME / "user_analytics.db"))
    data_root: Path = DATA_ROOT

    genome_db_dir: Path = Path(os.getenv("CUAGENT_GENOME_DB_DIR", _GENES / "Database_Outputs"))
    chroma_db_path: Path = Path(os.getenv("CUAGENT_CHROMA_DB", DATA_ROOT / "literature" / "chroma_cucurbit_db_v4"))
    literature_db_path: Path = Path(
        os.getenv("CUAGENT_LITERATURE_DB", DATA_ROOT / "literature" / "Cucurbit_Papers_v4.db")
    )
    genome_data_module: Path = Path(os.getenv("CUAGENT_GENOME_DATA_MODULE", DATA_ROOT / "downloads"))
    web_structure_dir: Path = Path(os.getenv("CUAGENT_WEB_STRUCTURE", DATA_ROOT / "structures"))

    # 9-species standardized transcriptome data (parquet).
    expression_dir: Path = Path(os.getenv("CUAGENT_EXPRESSION_DIR", DATA_ROOT / "expression"))

    homology_db: Path = genome_db_dir / "Homology_Engine_V2" / "Pan_Plant_Homologs_V2.db"
    variant_index_db: Path = genome_db_dir / "Variant_Index.db"

    cucumber_gff3: Path = _GENES / "Cucumber" / "Cucumber_v3" / "ChineseLong_v3.gff3.gz"
    # Prefer pfam2go-filled GAF (original *.gaf.txt.gz kept as backup sibling).
    cucumber_go_gaf: Path = _GENES / "Cucumber" / "Cucumber_v3" / "ChineseLong_GO_v3.gaf.filled.txt.gz"
    cucumber_domains: Path = _GENES / "Cucumber" / "Cucumber_v3" / "Cucumber_V3_Domains.tsv"
    cucumber_synteny: Path = _GENES / "Cucumber" / "Cucumber_v3" / "Cucumber_V3_Hardwickii_Synteny_Orthologs.tsv"

    watermelon_gff3: Path = _GENES / "Watermelon" / "Watermelon_v2.5" / "97103_v2.5.gff3.gz"
    watermelon_go_gaf: Path = _GENES / "Watermelon" / "Watermelon_v2.5" / "97103_GO_v2.5.gaf.filled.txt.gz"
    watermelon_domains: Path = _GENES / "Watermelon" / "Watermelon_v2.5" / "Watermelon_V2.5_Domains.tsv"

    melon_gff3: Path = _GENES / "Melon" / "Melon_v4.0" / "DHL92_v4.gff3.gz"
    melon_go_gaf: Path = _GENES / "Melon" / "Melon_v4.0" / "DHL92_GO_v4.gaf.filled.txt.gz"
    melon_domains: Path = _GENES / "Melon" / "Melon_v4.0" / "Melon_V4_Domains.tsv"

    pumpkin_moschata_gff3: Path = _GENES / "Pumpkin_Squash" / "Cucurbita_moschata" / "v1" / "Cmoschata_v1.gff3.gz"
    pumpkin_moschata_go_gaf: Path = (
        _GENES / "Pumpkin_Squash" / "Cucurbita_moschata" / "v1" / "Cmoschata_GO_v1.gaf.filled.txt.gz"
    )
    pumpkin_moschata_mapping: Path = (
        _GENES / "Pumpkin_Squash" / "Cucurbita_moschata" / "Cmoschata_MASTER_V1_V2_Mapping.tsv"
    )
    pumpkin_moschata_domains: Path = (
        _GENES / "Pumpkin_Squash" / "Cucurbita_moschata" / "v1" / "Cmoschata_V1_Domains.tsv"
    )

    pumpkin_pepo_gff3: Path = _GENES / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_v4.1.gff3.gz"
    pumpkin_pepo_go_gaf: Path = (
        _GENES / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_GO_v4.1.gaf.filled.txt.gz"
    )
    pumpkin_pepo_domains: Path = (
        _GENES / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_V4.1_Domains.tsv"
    )

    bittergourd_gff3: Path = _GENES / "BitterGourd" / "OHB3-1" / "OHB3-1_v2.gff3.gz"
    bittergourd_go_gaf: Path = _GENES / "BitterGourd" / "OHB3-1" / "OHB3-1_GO_v2.gaf.filled.txt.gz"
    bittergourd_domains: Path = _GENES / "BitterGourd" / "OHB3-1" / "BitterGourd_V2_Domains.tsv"

    bottlegourd_gff3: Path = _GENES / "BottleGourd" / "USVL1VR-Ls" / "USVL1VR-Ls_v1.gff3.gz"
    bottlegourd_go_gaf: Path = _GENES / "BottleGourd" / "USVL1VR-Ls" / "USVL1VR-Ls_GO_v1.gaf.filled.txt.gz"
    bottlegourd_domains: Path = _GENES / "BottleGourd" / "USVL1VR-Ls" / "BottleGourd_V1_Domains.tsv"

    waxgourd_gff3: Path = _GENES / "WaxGourd" / "WG.gff3.gz"
    waxgourd_go_gaf: Path = _GENES / "WaxGourd" / "WG_GO.gaf.filled.txt.gz"
    waxgourd_domains: Path = _GENES / "WaxGourd" / "WG_Domains.tsv"

    spongegourd_gff3: Path = _GENES / "SpongeGourd" / "L_cylindrica" / "L_cylindrica.gff3.gz"
    spongegourd_go_gaf: Path = _GENES / "SpongeGourd" / "L_cylindrica" / "L_cylindrica_GO.gaf.filled.txt.gz"
    spongegourd_domains: Path = _GENES / "SpongeGourd" / "L_cylindrica" / "SpongeGourd_Domains.tsv"

    gpsite_csv: Path = web_structure_dir / "cucu_v3_pdb_site" / "ChineseLong_v3_GPSite_Final.csv"
    residue_sites_dir: Path = web_structure_dir / "cucu_v3_pdb_site" / "all_sites_json"

    embed_model_name: str = os.getenv("CUAGENT_EMBED_MODEL", "BAAI/bge-m3")
    embed_model_local: str = os.getenv("CUAGENT_EMBED_MODEL_LOCAL", "")

    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")
    zhipu_base_url: str = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
    zhipu_model: str = os.getenv("ZHIPU_MODEL", "glm-5.1")
    # LLM provider-specific kwargs passed through `extra_body` on every chat
    # completion call. Centralised here so all 10 call sites stay in sync.
    # DeepSeek V4 defaults to thinking=enabled (returns reasoning_content,
    # adds latency + token cost). Set CUAGENT_LLM_THINKING=enabled to opt in.
    _thinking_type = os.getenv("CUAGENT_LLM_THINKING", "disabled").strip().lower()
    llm_extra_body: dict = {"thinking": {"type": _thinking_type}}

    admin_api_token: str = os.getenv("CUAGENT_ADMIN_TOKEN", "")
    llm_rate_limit_per_minute: int = int(os.getenv("CUAGENT_LLM_RATE_LIMIT_PER_MIN", "10"))
    llm_rate_limit_per_day: int = int(os.getenv("CUAGENT_LLM_RATE_LIMIT_PER_DAY", "20"))
    llm_rate_limit_per_user_day: int = int(os.getenv("CUAGENT_LLM_RATE_LIMIT_PER_USER_DAY", "20"))
    llm_rate_limit_per_ip_day: int = int(os.getenv("CUAGENT_LLM_RATE_LIMIT_PER_IP_DAY", "40"))
    require_auth_for_llm: str = os.getenv("CUAGENT_REQUIRE_AUTH_FOR_LLM", "1")
    llm_max_message_chars: int = int(os.getenv("CUAGENT_LLM_MAX_MESSAGE_CHARS", "4000"))
    llm_max_history_turns: int = int(os.getenv("CUAGENT_LLM_MAX_HISTORY_TURNS", "12"))
    llm_max_history_chars: int = int(os.getenv("CUAGENT_LLM_MAX_HISTORY_CHARS", "2000"))
    download_rate_limit_per_hour: int = int(os.getenv("CUAGENT_DOWNLOAD_RATE_LIMIT_PER_HOUR", "40"))
    ip_hash_salt: str = os.getenv("CUAGENT_IP_HASH_SALT", "cuagent")
    trusted_proxies: str = os.getenv("CUAGENT_TRUSTED_PROXIES", "")
    env: str = os.getenv("CUAGENT_ENV", "development").strip().lower()
    cors_origins: str = os.getenv("CUAGENT_CORS_ORIGINS", "")
    disable_docs: str = os.getenv("CUAGENT_DISABLE_DOCS", "")

    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_use_ssl: str = os.getenv("SMTP_USE_SSL", "1")

    analytics_retention_days: int = int(os.getenv("CUAGENT_ANALYTICS_RETENTION_DAYS", "90"))

    # ---- Privacy policy / terms versioning ----
    # Bump these whenever the policy/terms meaningfully change; the frontend
    # compares a user's stored privacy_version against privacy_version to decide
    # whether to prompt for re-consent on next login.
    privacy_version: str = os.getenv("CUAGENT_PRIVACY_VERSION", "v1.0")
    privacy_policy_updated_at: str = os.getenv(
        "CUAGENT_PRIVACY_UPDATED_AT", "2026-07-29"
    )
    terms_version: str = os.getenv("CUAGENT_TERMS_VERSION", "v1.0")
    # Public contact for data-protection / privacy inquiries. Default is the
    # institutional mailbox declared in content/home.json.
    privacy_contact_email: str = os.getenv(
        "CUAGENT_PRIVACY_CONTACT_EMAIL", "privacy@your-domain.example"
    )

    def validate_ai_config(self) -> tuple[bool, str]:
        """Return (ok, reason). Routes can use this to emit a clean 503
        instead of letting the OpenAI client raise deep inside a stream."""
        if not self.zhipu_api_key:
            return False, "ZHIPU_API_KEY is not configured on the server."
        if not self.zhipu_base_url:
            return False, "ZHIPU_BASE_URL is empty."
        return True, ""

    bvrc_hq_lat: float = 39.9589
    bvrc_hq_lon: float = 116.2988

    @property
    def global_search_config(self) -> dict:
        d = self.genome_db_dir
        return {
            "Watermelon": str(d / "Watermelon_V2.5_Master_Database.tsv"),
            "Cucumber": str(d / "Cucumber_V3_Master_Database.tsv"),
            "Melon": str(d / "Melon_V4_Master_Database.tsv"),
            "Pumpkin (C. moschata)": str(d / "Pumpkin_Moschata_V2_Master_Database.tsv"),
            "Pumpkin (C. pepo)": str(d / "Pumpkin_Pepo_Master_Database.tsv"),
            "BitterGourd": str(d / "BitterGourd_Master_Database.tsv"),
            "BottleGourd": str(d / "BottleGourd_Master_Database.tsv"),
            "WaxGourd": str(d / "WaxGourd_Master_Database.tsv"),
            "SpongeGourd": str(d / "SpongeGourd_Master_Database.tsv"),
        }

    @property
    def global_map_config(self) -> dict:
        g = _GENES
        return {
            "Watermelon": str(g / "Watermelon" / "Watermelon_MASTER_V1_V2_V2.5_Mapping.tsv"),
            "Cucumber": str(g / "Cucumber" / "Cucumber_MASTER_V1_V2_V3_Mapping.tsv"),
            "Melon": str(g / "Melon" / "Melon_MASTER_V3.5.1_V3.6.1_V4.0_Mapping.tsv"),
            "Pumpkin (C. moschata)": str(
                g / "Pumpkin_Squash" / "Cucurbita_moschata" / "Cmoschata_MASTER_V1_V2_Mapping.tsv"
            ),
        }

    @property
    def species_gff3(self) -> dict:
        """GFF3 path per species (master-DB display name -> gff3 file)."""
        return {
            "Cucumber": self.cucumber_gff3,
            "Watermelon": self.watermelon_gff3,
            "Melon": self.melon_gff3,
            "Pumpkin (C. moschata)": self.pumpkin_moschata_gff3,
            "Pumpkin (C. pepo)": self.pumpkin_pepo_gff3,
            "BitterGourd": self.bittergourd_gff3,
            "BottleGourd": self.bottlegourd_gff3,
            "WaxGourd": self.waxgourd_gff3,
            "SpongeGourd": self.spongegourd_gff3,
        }

    @property
    def species_go_gaf(self) -> dict:
        """GO GAF path per species (master-DB display name -> gaf file)."""
        return {
            "Cucumber": self.cucumber_go_gaf,
            "Watermelon": self.watermelon_go_gaf,
            "Melon": self.melon_go_gaf,
            "Pumpkin (C. moschata)": self.pumpkin_moschata_go_gaf,
            "Pumpkin (C. pepo)": self.pumpkin_pepo_go_gaf,
            "BitterGourd": self.bittergourd_go_gaf,
            "BottleGourd": self.bottlegourd_go_gaf,
            "WaxGourd": self.waxgourd_go_gaf,
            "SpongeGourd": self.spongegourd_go_gaf,
        }

    @property
    def species_pfam_domains(self) -> dict:
        """Pfam domains TSV per species (master-DB display name -> tsv file).

        Generated by ``scripts/run_pfam_all_species.py``. Files may not exist
        for every species until that script has been run; callers should check
        ``os.path.exists`` before reading.
        """
        return {
            "Cucumber": self.cucumber_domains,
            "Watermelon": self.watermelon_domains,
            "Melon": self.melon_domains,
            "Pumpkin (C. moschata)": self.pumpkin_moschata_domains,
            "Pumpkin (C. pepo)": self.pumpkin_pepo_domains,
            "BitterGourd": self.bittergourd_domains,
            "BottleGourd": self.bottlegourd_domains,
            "WaxGourd": self.waxgourd_domains,
            "SpongeGourd": self.spongegourd_domains,
        }


settings = Settings()
