"""Sprite manager for loading and managing sprites for the world visualization."""

import json
from pathlib import Path
from typing import Dict, Optional

from world.avatar_generator import AvatarGenerator


class SpriteManager:
    """Manages sprite loading and provides sprite paths/URLs."""

    def __init__(self, sprite_dir: str = "./sprites"):
        """Initialize sprite manager.

        Args:
            sprite_dir: Directory containing sprite images
        """
        self.sprite_dir = Path(sprite_dir)
        self.sprite_dir.mkdir(exist_ok=True)
        self._sprite_cache: Dict[str, str] = {}
        self._load_sprite_manifest()

    def _load_sprite_manifest(self) -> None:
        """Load sprite manifest if it exists."""
        manifest_path = self.sprite_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                    self._sprite_cache = manifest.get("sprites", {})
            except Exception:
                pass

    def get_terrain_sprite(
        self, terrain_type: str, use_http_url: bool = True
    ) -> Optional[str]:
        """Get sprite path for a terrain type.

        Args:
            terrain_type: Type of terrain (grass, water, stone, etc.)
            use_http_url: If True, return HTTP URL path; if False, return file path

        Returns:
            Path to sprite image (HTTP URL or file path), or None if not found
        """
        # Check cache first
        cache_key = f"terrain_{terrain_type}"
        if cache_key in self._sprite_cache:
            cached_path = self._sprite_cache[cache_key]
            # If cache has HTTP URL, return it; otherwise convert if needed
            if use_http_url and not cached_path.startswith("/sprites/"):
                sprite_filename = f"terrain_{terrain_type}.png"
                return f"/sprites/{sprite_filename}"
            return cached_path

        # Check for sprite file
        sprite_file = self.sprite_dir / f"terrain_{terrain_type}.png"
        if sprite_file.exists():
            if use_http_url:
                return f"/sprites/terrain_{terrain_type}.png"
            else:
                return str(sprite_file.relative_to(Path.cwd()))

        return None

    def get_creature_sprite(
        self,
        creature_name: str,
        use_http_url: bool = True,
        description: str = "",
        personality: str = "",
    ) -> Optional[str]:
        """Get sprite path for a creature. Generates SVG avatar if no static image exists.

        Args:
            creature_name: Name of the creature
            use_http_url: If True, return HTTP URL path; if False, return file path
            description: Creature description for avatar generation
            personality: Creature personality for avatar generation

        Returns:
            Path to sprite image (HTTP URL, file path, or data URL), or None if not found
        """
        # Check cache first
        cache_key = f"creature_{creature_name.lower()}"
        if cache_key in self._sprite_cache:
            cached_path = self._sprite_cache[cache_key]
            # If cache has HTTP URL, return it; otherwise convert if needed
            if use_http_url and not cached_path.startswith("/sprites/"):
                sprite_filename = f"creature_{creature_name.lower()}.png"
                return f"/sprites/{sprite_filename}"
            return cached_path

        # Check for sprite file
        sprite_file = self.sprite_dir / f"creature_{creature_name.lower()}.png"
        if sprite_file.exists():
            if use_http_url:
                return f"/sprites/creature_{creature_name.lower()}.png"
            else:
                return str(sprite_file.relative_to(Path.cwd()))

        # Generate SVG avatar as fallback
        avatar_url: str = AvatarGenerator.generate_data_url(
            creature_name, description, personality
        )
        return avatar_url

    def get_item_sprite(
        self, item_name: str, use_http_url: bool = True
    ) -> Optional[str]:
        """Get sprite path for an item.

        Args:
            item_name: Name of the item
            use_http_url: If True, return HTTP URL path; if False, return file path

        Returns:
            Path to sprite image (HTTP URL or file path), or None if not found
        """
        cache_key = f"item_{item_name.lower()}"
        if cache_key in self._sprite_cache:
            cached_path = self._sprite_cache[cache_key]
            # If cache has HTTP URL, return it; otherwise convert if needed
            if use_http_url and not cached_path.startswith("/sprites/"):
                sprite_filename = f"item_{item_name.lower()}.png"
                return f"/sprites/{sprite_filename}"
            return cached_path

        sprite_file = self.sprite_dir / f"item_{item_name.lower()}.png"
        if sprite_file.exists():
            if use_http_url:
                return f"/sprites/item_{item_name.lower()}.png"
            else:
                return str(sprite_file.relative_to(Path.cwd()))

        return None

    def has_sprites(self) -> bool:
        """Check if any sprites are available."""
        return len(self._sprite_cache) > 0 or any(self.sprite_dir.glob("*.png"))


# Default sprite manager instance
_default_sprite_manager: Optional[SpriteManager] = None


def get_sprite_manager(sprite_dir: str = "./sprites") -> SpriteManager:
    """Get or create the default sprite manager."""
    global _default_sprite_manager
    if _default_sprite_manager is None:
        _default_sprite_manager = SpriteManager(sprite_dir)
    return _default_sprite_manager
