"""Import a single navigation map into a semantic world file."""

from __future__ import annotations

import argparse
from pathlib import Path

from fishmindos.adapters import create_fishbot_adapter
from fishmindos.config import get_config
from fishmindos.world import WorldBuilder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import one nav map into a FishMindOS world file.")
    parser.add_argument("--map-name", help="Navigation map name to import")
    parser.add_argument("--map-id", type=int, help="Navigation map id to import")
    parser.add_argument("--world-path", help="Target world JSON path")
    parser.add_argument("--world-name", help="World name to write into the file")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append locations for this map instead of replacing old locations from the same map",
    )
    parser.add_argument(
        "--no-set-default",
        action="store_true",
        help="Do not set the imported map as this world's default map",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.map_name is None and args.map_id is None:
        parser.error("one of --map-name or --map-id is required")

    config = get_config()
    world_path = args.world_path or config.world.path
    world_path_obj = Path(world_path)
    if not world_path_obj.is_absolute():
        world_path_obj = Path.cwd() / world_path_obj

    adapter = create_fishbot_adapter(
        nav_server_host=config.nav_server.host,
        nav_server_port=config.nav_server.port,
        nav_app_host=config.nav_app.host,
        nav_app_port=config.nav_app.port,
        rosbridge_host=config.rosbridge.host,
        rosbridge_port=config.rosbridge.port,
        rosbridge_path=config.rosbridge.path,
    )

    try:
        health = adapter.connect()
        if not health.get("nav_server", {}).get("connected"):
            nav_error = health.get("nav_server", {}).get("error") or "nav_server unavailable"
            raise RuntimeError(nav_error)

        builder = WorldBuilder(adapter)
        world = builder.import_map_to_world(
            world_path=world_path_obj,
            map_name=args.map_name,
            map_id=args.map_id,
            world_name=args.world_name,
            replace_map_locations=not args.append,
            set_default=not args.no_set_default,
        )
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass

    default_map = world.default_map_name or world.default_map_id or "未设置"
    print(f"World imported: {world.name}")
    print(f"World file: {world_path_obj}")
    print(f"Default map: {default_map}")
    print(f"Maps: {len(world.maps)}")
    print(f"Locations: {len(world.locations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
