import { callable } from "@decky/api";

export type Profile = "default" | "quality" | "balanced" | "performance";

export const PROFILES: { id: Profile; label: string }[] = [
  { id: "default", label: "Default (original)" },
  { id: "quality", label: "Quality" },
  { id: "balanced", label: "Balanced" },
  { id: "performance", label: "Performance" },
];

// profile_device: whose profiles to borrow when the game has none for this device (null: none, nothing is set).
export interface GameSettings { profile: Profile; profile_device?: string | null }
export interface Settings {
  schema_version: number;
  global_profile: null;
  games: Record<string, GameSettings>;
  game_filter: GameFilter;
  last_game: number | null;
}
export interface Bootstrap {
  settings: Settings;
  device: string;  // detected, else "generic"
  fps_targets: Record<Profile, number | null>;  // each profile's target FPS on this device (shown only)
  devices: { id: string; name: string }[];
}
export type GameFilter = "verified" | "loadout";
export interface Game {
  appid: number; name: string; supported: boolean; verified: boolean; profile: Profile | null;
  devices: string[];  // devices the game has Loadout profiles for
  // Per device: its profiles (one it leaves out is hidden) with the recommended "WIDTHxHEIGHT", if any.
  profiles: Record<string, Partial<Record<Profile, string | null>>>;
}
export interface Change { kind: string; target: string; key: string; old: string | null; new: string | null }
export interface Plan {
  appid: number;
  profile: Profile;
  launch_options: string;
  changes: Change[];
  warnings: string[];
  blocked: boolean;
  file_writes: [path: string, values: Record<string, string>][];
}
export interface ApplyResult { launch_options: string; warnings: string[]; applied: boolean }

export const getBootstrap = callable<[], Bootstrap>("get_bootstrap");
export const listGames = callable<[], Game[]>("list_games");
export const setGameFilter = callable<[filter: GameFilter], Settings>("set_game_filter");
export const resetSettings = callable<[], Settings>("reset_settings");
export const planProfile =
  callable<[appid: number, profile: Profile, current: string, profileDevice: string | null], Plan>(
    "plan_profile");
export const applyProfile =
  callable<[appid: number, profile: Profile, current: string, profileDevice: string | null],
    ApplyResult>("apply_profile");

// Steam client internals (not a public contract): read/write a game's launch options.
export function getLaunchOptions(appid: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Steam did not return app details")), 5000);
    const reg = window.SteamClient.Apps.RegisterForAppDetails(appid, (details) => {
      clearTimeout(timer);
      setTimeout(() => reg.unregister());
      resolve(details.strLaunchOptions ?? "");
    });
  });
}

export function setLaunchOptions(appid: number, options: string): void {
  window.SteamClient.Apps.SetAppLaunchOptions(appid, options);
}
