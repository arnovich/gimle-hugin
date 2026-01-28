"""Generate unique SVG avatars for creatures based on their characteristics."""

import hashlib
from typing import Tuple


class AvatarGenerator:
    """Generate procedural SVG avatars for creatures."""

    # Color palettes for different creature types
    PALETTES = {
        "warm": [
            "#FF6B6B",
            "#FFA07A",
            "#FFD93D",
            "#FF8C42",
            "#FF6347",
        ],
        "cool": [
            "#6BCF7F",
            "#4ECDC4",
            "#45B7D1",
            "#5F9EA0",
            "#6A8EAE",
        ],
        "pastel": [
            "#FFB6C1",
            "#FFE4E1",
            "#E0BBE4",
            "#D4A5A5",
            "#FFDAC1",
        ],
        "vibrant": [
            "#FF0080",
            "#7928CA",
            "#0070F3",
            "#00DFD8",
            "#7EE081",
        ],
        "earth": [
            "#8B4513",
            "#D2691E",
            "#CD853F",
            "#DEB887",
            "#F4A460",
        ],
    }

    @staticmethod
    def _hash_string(text: str) -> int:
        """Create a deterministic hash from a string."""
        return int(hashlib.md5(text.encode()).hexdigest(), 16)

    @staticmethod
    def _get_color_from_hash(hash_val: int, palette: str = "pastel") -> str:
        """Get a color from a palette based on hash value."""
        colors = AvatarGenerator.PALETTES.get(
            palette, AvatarGenerator.PALETTES["pastel"]
        )
        return colors[hash_val % len(colors)]

    @staticmethod
    def _get_head_from_hash(
        hash_val: int,
    ) -> Tuple[str, str]:  # (head_type, svg_element)
        """Get a head shape and its SVG representation based on hash."""
        heads = [
            ("circle", '<circle cx="50" cy="22" r="16"/>'),
            (
                "rounded_square",
                '<rect x="34" y="6" width="32" height="32" rx="10"/>',
            ),
            ("oval", '<ellipse cx="50" cy="22" rx="14" ry="18"/>'),
            (
                "super_rounded",
                '<rect x="34" y="6" width="32" height="32" rx="16"/>',
            ),
            ("squircle", '<circle cx="50" cy="22" r="15"/>'),
            # New shapes
            (
                "bean",
                '<ellipse cx="50" cy="22" rx="16" ry="14" '
                'transform="rotate(-10 50 22)"/>',
            ),
            (
                "heart",
                '<path d="M 50 38 C 34 38 30 22 38 14 Q 50 6 50 16 '
                'Q 50 6 62 14 C 70 22 66 38 50 38 Z"/>',
            ),
            (
                "diamond",
                '<path d="M 50 6 L 66 22 L 50 38 L 34 22 Z" rx="3"/>',
            ),
            (
                "wide",
                '<ellipse cx="50" cy="22" rx="18" ry="12"/>',
            ),
        ]
        return heads[hash_val % len(heads)]

    @staticmethod
    def _get_pose_from_hash(hash_val: int) -> Tuple[str, str]:
        """Get a pose and its SVG representation based on hash."""
        poses = [
            # Standing straight - shorter, chubbier
            (
                "standing",
                """
                <!-- Body -->
                <line x1="50" y1="38" x2="50" y2="58" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Arms - chubby -->
                <line x1="50" y1="45" x2="35" y2="53" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="45" x2="65" y2="53" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Hands -->
                <circle cx="35" cy="53" r="3" fill="#000"/>
                <circle cx="65" cy="53" r="3" fill="#000"/>
                <!-- Legs - short and chubby -->
                <line x1="50" y1="58" x2="42" y2="75" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="58" x2="58" y2="75" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Feet -->
                <ellipse cx="42" cy="77" rx="5" ry="3" fill="#000"/>
                <ellipse cx="58" cy="77" rx="5" ry="3" fill="#000"/>
                """,
            ),
            # Walking - cute waddle
            (
                "walking",
                """
                <!-- Body -->
                <line x1="50" y1="38" x2="50" y2="58" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Arms swinging -->
                <line x1="50" y1="45" x2="38" y2="56" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="45" x2="62" y2="50" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Hands -->
                <circle cx="38" cy="56" r="3" fill="#000"/>
                <circle cx="62" cy="50" r="3" fill="#000"/>
                <!-- Legs walking -->
                <line x1="50" y1="58" x2="45" y2="75" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="58" x2="56" y2="73" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Feet -->
                <ellipse cx="45" cy="77" rx="5" ry="3" fill="#000"/>
                <ellipse cx="56" cy="75" rx="5" ry="3" fill="#000"/>
                """,
            ),
            # Waving - excited!
            (
                "waving",
                """
                <!-- Body -->
                <line x1="50" y1="38" x2="50" y2="58" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Arms - one waving up -->
                <line x1="50" y1="45" x2="38" y2="52" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="45" x2="68" y2="30" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Hands -->
                <circle cx="38" cy="52" r="3" fill="#000"/>
                <circle cx="68" cy="30" r="4" fill="#000"/>
                <!-- Legs -->
                <line x1="50" y1="58" x2="42" y2="75" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="58" x2="58" y2="75" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Feet -->
                <ellipse cx="42" cy="77" rx="5" ry="3" fill="#000"/>
                <ellipse cx="58" cy="77" rx="5" ry="3" fill="#000"/>
                """,
            ),
            # Jumping - super excited!
            (
                "jumping",
                """
                <!-- Body -->
                <line x1="50" y1="38" x2="50" y2="56" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Arms up -->
                <line x1="50" y1="42" x2="38" y2="32" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="42" x2="62" y2="32" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Hands -->
                <circle cx="38" cy="32" r="4" fill="#000"/>
                <circle cx="62" cy="32" r="4" fill="#000"/>
                <!-- Legs bent -->
                <line x1="50" y1="56" x2="43" y2="72" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="56" x2="57" y2="72" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Feet -->
                <ellipse cx="43" cy="74" rx="5" ry="3" fill="#000"/>
                <ellipse cx="57" cy="74" rx="5" ry="3" fill="#000"/>
                """,
            ),
            # Sitting - adorable
            (
                "sitting",
                """
                <!-- Body -->
                <line x1="50" y1="38" x2="50" y2="54" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Arms resting -->
                <line x1="50" y1="45" x2="40" y2="54" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="45" x2="60" y2="54" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Hands -->
                <circle cx="40" cy="54" r="3" fill="#000"/>
                <circle cx="60" cy="54" r="3" fill="#000"/>
                <!-- Legs bent forward -->
                <line x1="50" y1="54" x2="38" y2="58" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="38" y1="58" x2="32" y2="68" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="50" y1="54" x2="62" y2="58" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <line x1="62" y1="58" x2="68" y2="68" stroke="#000" stroke-width="5" stroke-linecap="round"/>
                <!-- Feet -->
                <ellipse cx="32" cy="70" rx="5" ry="3" fill="#000"/>
                <ellipse cx="68" cy="70" rx="5" ry="3" fill="#000"/>
                """,
            ),
        ]
        return poses[hash_val % len(poses)]

    @staticmethod
    def _get_eyes_from_hash(hash_val: int) -> str:
        """Generate eye elements based on hash (positioned for head at y=22)."""
        eye_styles = [
            # Big sparkly eyes
            '<circle cx="44" cy="20" r="4" fill="#FFF" stroke="#000" stroke-width="1.5"/>'
            '<circle cx="44" cy="19.5" r="2" fill="#000"/>'
            '<circle cx="45" cy="18.5" r="1" fill="#FFF"/>'
            '<circle cx="56" cy="20" r="4" fill="#FFF" stroke="#000" stroke-width="1.5"/>'
            '<circle cx="56" cy="19.5" r="2" fill="#000"/>'
            '<circle cx="57" cy="18.5" r="1" fill="#FFF"/>',
            # Giant kawaii eyes
            '<circle cx="44" cy="20" r="5" fill="#FFF" stroke="#000" stroke-width="2"/>'
            '<circle cx="44" cy="20" r="2.5" fill="#000"/>'
            '<circle cx="45.5" cy="18.5" r="1.5" fill="#FFF"/>'
            '<circle cx="56" cy="20" r="5" fill="#FFF" stroke="#000" stroke-width="2"/>'
            '<circle cx="56" cy="20" r="2.5" fill="#000"/>'
            '<circle cx="57.5" cy="18.5" r="1.5" fill="#FFF"/>',
            # Happy closed eyes
            '<path d="M 41 20 Q 44 17 47 20" stroke="#000" stroke-width="2" fill="none" stroke-linecap="round"/>'
            '<path d="M 53 20 Q 56 17 59 20" stroke="#000" stroke-width="2" fill="none" stroke-linecap="round"/>',
            # Starry eyes
            '<circle cx="44" cy="20" r="4.5" fill="#FFF" stroke="#000" stroke-width="1.5"/>'
            '<circle cx="44" cy="20" r="2.2" fill="#000"/>'
            '<path d="M 44 17 L 44.5 18.5 L 46 18.5 L 44.8 19.3 L 45.3 21 L 44 20 L 42.7 21 L 43.2 19.3 L 42 18.5 L 43.5 18.5 Z" fill="#FFF" opacity="0.8"/>'
            '<circle cx="56" cy="20" r="4.5" fill="#FFF" stroke="#000" stroke-width="1.5"/>'
            '<circle cx="56" cy="20" r="2.2" fill="#000"/>'
            '<path d="M 56 17 L 56.5 18.5 L 58 18.5 L 56.8 19.3 L 57.3 21 L 56 20 L 54.7 21 L 55.2 19.3 L 54 18.5 L 55.5 18.5 Z" fill="#FFF" opacity="0.8"/>',
            # Round curious eyes
            '<circle cx="44" cy="20" r="4" fill="#000"/>'
            '<circle cx="45" cy="19" r="1.5" fill="#FFF"/>'
            '<circle cx="56" cy="20" r="4" fill="#000"/>'
            '<circle cx="57" cy="19" r="1.5" fill="#FFF"/>',
            # New styles - Sleepy eyes
            '<path d="M 41 21 Q 44 19 47 21" stroke="#000" stroke-width="2.5" '
            'fill="none" stroke-linecap="round"/>'
            '<path d="M 53 21 Q 56 19 59 21" stroke="#000" stroke-width="2.5" '
            'fill="none" stroke-linecap="round"/>',
            # Angry/determined eyes with angled brows
            '<path d="M 40 16 L 48 19" stroke="#000" stroke-width="2"/>'
            '<circle cx="44" cy="20" r="3" fill="#000"/>'
            '<circle cx="45" cy="19" r="1" fill="#FFF"/>'
            '<path d="M 60 16 L 52 19" stroke="#000" stroke-width="2"/>'
            '<circle cx="56" cy="20" r="3" fill="#000"/>'
            '<circle cx="57" cy="19" r="1" fill="#FFF"/>',
            # Heart eyes
            '<path d="M 44 22 C 42 20 40 18 42 16 C 44 14 44 16 44 16 '
            'C 44 16 44 14 46 16 C 48 18 46 20 44 22 Z" fill="#FF6B6B"/>'
            '<path d="M 56 22 C 54 20 52 18 54 16 C 56 14 56 16 56 16 '
            'C 56 16 56 14 58 16 C 60 18 58 20 56 22 Z" fill="#FF6B6B"/>',
            # Wide surprised eyes
            '<circle cx="44" cy="20" r="5" fill="#FFF" stroke="#000" stroke-width="2"/>'
            '<circle cx="44" cy="20" r="3" fill="#000"/>'
            '<circle cx="45" cy="19" r="1" fill="#FFF"/>'
            '<circle cx="56" cy="20" r="5" fill="#FFF" stroke="#000" stroke-width="2"/>'
            '<circle cx="56" cy="20" r="3" fill="#000"/>'
            '<circle cx="57" cy="19" r="1" fill="#FFF"/>',
        ]
        return eye_styles[hash_val % len(eye_styles)]

    @staticmethod
    def _get_mouth_from_hash(hash_val: int) -> str:
        """Generate mouth element based on hash (positioned for head at y=22)."""
        mouth_styles = [
            # Big cute smile
            '<path d="M 42 26 Q 50 30 58 26" stroke="#000" stroke-width="2" fill="none" stroke-linecap="round"/>',
            # Cat smile
            '<path d="M 44 26 Q 47 28 50 27 Q 53 28 56 26" stroke="#000" stroke-width="2" fill="none" stroke-linecap="round"/>',
            # Tiny "o" mouth
            '<circle cx="50" cy="27" r="2.5" fill="#000"/>',
            # Happy open mouth
            '<ellipse cx="50" cy="27" rx="4" ry="3" fill="#000"/>'
            '<ellipse cx="50" cy="26.5" rx="3" ry="2" fill="#FFA0A0"/>',
            # Determined smile
            '<line x1="44" y1="27" x2="56" y2="27" stroke="#000" stroke-width="2.5" stroke-linecap="round"/>',
            # New styles - Surprised "O"
            '<ellipse cx="50" cy="27" rx="3" ry="4" fill="#000"/>',
            # Mischievous grin with fang
            '<path d="M 44 26 Q 50 30 56 26" stroke="#000" stroke-width="2" '
            'fill="none" stroke-linecap="round"/>'
            '<path d="M 54 26 L 55 29 L 56 26" fill="#FFF"/>',
            # Tongue out
            '<path d="M 44 26 Q 50 29 56 26" stroke="#000" stroke-width="2" '
            'fill="none" stroke-linecap="round"/>'
            '<ellipse cx="50" cy="29" rx="3" ry="2" fill="#FF9999"/>',
            # Sad frown
            '<path d="M 44 28 Q 50 25 56 28" stroke="#000" stroke-width="2" '
            'fill="none" stroke-linecap="round"/>',
        ]
        return mouth_styles[hash_val % len(mouth_styles)]

    @staticmethod
    def _get_accessories_from_hash(hash_val: int, base_color: str) -> str:
        """Generate accessory elements based on hash."""
        accessories = [
            # Top hat
            f'<rect x="38" y="2" width="24" height="4" rx="2" fill="{base_color}"/>'
            f'<rect x="42" y="4" width="16" height="4" fill="{base_color}"/>',
            # Bow on head
            f'<ellipse cx="42" cy="8" rx="5" ry="4" fill="{base_color}"/>'
            f'<ellipse cx="58" cy="8" rx="5" ry="4" fill="{base_color}"/>'
            f'<circle cx="50" cy="8" r="3" fill="{base_color}"/>',
            # Cute bow tie
            f'<polygon points="45,38 48,40 45,42" fill="{base_color}"/>'
            f'<polygon points="55,38 52,40 55,42" fill="{base_color}"/>'
            f'<circle cx="50" cy="40" r="2" fill="{base_color}"/>',
            # Little cape
            f'<path d="M 35 42 Q 35 48 38 52 L 38 38 Z" fill="{base_color}" '
            f'opacity="0.8"/>'
            f'<path d="M 65 42 Q 65 48 62 52 L 62 38 Z" fill="{base_color}" '
            f'opacity="0.8"/>',
            # Heart badge
            f'<path d="M 50 42 C 48 40 45 40 45 43 C 45 45 47 47 50 49 '
            f'C 53 47 55 45 55 43 C 55 40 52 40 50 42 Z" fill="{base_color}"/>',
            # Nothing (minimal)
            "",
            # New accessories - Crown
            f'<path d="M 38 6 L 42 2 L 46 6 L 50 0 L 54 6 L 58 2 L 62 6 '
            f'L 60 10 L 40 10 Z" fill="{base_color}"/>'
            f'<circle cx="50" cy="4" r="2" fill="#FFF"/>',
            # Glasses
            '<circle cx="44" cy="20" r="5" fill="none" stroke="#333" '
            'stroke-width="1.5"/>'
            '<circle cx="56" cy="20" r="5" fill="none" stroke="#333" '
            'stroke-width="1.5"/>'
            '<line x1="49" y1="20" x2="51" y2="20" stroke="#333" '
            'stroke-width="1.5"/>',
            # Flower on head
            f'<circle cx="62" cy="10" r="5" fill="{base_color}"/>'
            f'<circle cx="62" cy="10" r="2" fill="#FFD700"/>',
            # Scarf
            f'<rect x="40" y="36" width="20" height="6" rx="2" '
            f'fill="{base_color}"/>'
            f'<path d="M 55 42 Q 58 50 55 58" stroke="{base_color}" '
            f'stroke-width="5" fill="none" stroke-linecap="round"/>',
            # Bandana
            f'<path d="M 34 14 Q 50 8 66 14" stroke="{base_color}" '
            f'stroke-width="4" fill="none"/>'
            f'<polygon points="66,14 72,20 70,16" fill="{base_color}"/>',
        ]
        return accessories[hash_val % len(accessories)]

    @classmethod
    def generate_avatar(
        cls,
        creature_name: str,
        description: str = "",
        personality: str = "",
    ) -> str:
        """Generate a unique stick-figure avatar for a creature.

        Args:
            creature_name: Name of the creature
            description: Optional description to influence appearance
            personality: Optional personality to influence colors

        Returns:
            SVG markup as a string
        """
        # Create deterministic hash from creature characteristics
        seed = f"{creature_name}:{description}:{personality}"
        hash_val = cls._hash_string(seed)

        # Derive different aspects from hash
        head_hash = hash_val >> 8
        pose_hash = hash_val >> 16
        color_hash = hash_val >> 24
        eyes_hash = hash_val >> 32
        mouth_hash = hash_val >> 40
        accessory_hash = hash_val >> 48

        # Determine palette based on personality keywords
        palette = "pastel"  # default
        if personality:
            personality_lower = personality.lower()
            if any(
                word in personality_lower
                for word in ["aggressive", "fierce", "bold"]
            ):
                palette = "vibrant"
            elif any(
                word in personality_lower
                for word in ["calm", "peaceful", "gentle"]
            ):
                palette = "cool"
            elif any(
                word in personality_lower
                for word in ["warm", "friendly", "cheerful"]
            ):
                palette = "warm"
            elif any(
                word in personality_lower
                for word in ["earthy", "grounded", "natural"]
            ):
                palette = "earth"

        # Get components
        base_color = cls._get_color_from_hash(color_hash, palette)
        secondary_color = cls._get_color_from_hash(color_hash + 1, palette)
        head_type, head_svg = cls._get_head_from_hash(head_hash)
        pose_type, pose_svg = cls._get_pose_from_hash(pose_hash)
        eyes_svg = cls._get_eyes_from_hash(eyes_hash)
        mouth_svg = cls._get_mouth_from_hash(mouth_hash)
        accessories = cls._get_accessories_from_hash(
            accessory_hash, secondary_color
        )

        # Build SVG with transparent background
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
    <!-- Stick figure body and limbs -->
    <g>
        {pose_svg}
    </g>

    <!-- Head -->
    <g fill="{base_color}" opacity="0.9">
        {head_svg}
    </g>

    <!-- Face -->
    <g>
        <!-- Eyes -->
        {eyes_svg}

        <!-- Mouth -->
        {mouth_svg}
    </g>

    <!-- Accessories -->
    <g>
        {accessories}
    </g>
</svg>"""

        return svg

    @classmethod
    def generate_data_url(
        cls,
        creature_name: str,
        description: str = "",
        personality: str = "",
    ) -> str:
        """Generate a data URL for the avatar that can be used directly in img src.

        Args:
            creature_name: Name of the creature
            description: Optional description
            personality: Optional personality

        Returns:
            Data URL string
        """
        svg = cls.generate_avatar(creature_name, description, personality)
        # URL-encode the SVG for data URL
        import urllib.parse

        encoded = urllib.parse.quote(svg)
        return f"data:image/svg+xml,{encoded}"
