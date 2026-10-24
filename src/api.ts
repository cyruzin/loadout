import { callable } from "@decky/api";

export type Profile = "default" | "quality" | "balanced" | "performance" | "uncapped";

export const PROFILES: { id: Profile; label: string }[] = [
  { id: "default", label: "Default (original)" },
  { id: "quality", label: "Quality" },
  { id: "balanced", label: "Balanced" },
  { id: "performance", label: "Performance" },
  { id: "uncapped", label: "Uncapped" },
];

export interface GameSettings { profile: Profile; resolution: string | null }
export interface Settings {
  schema_version: number;
  device: string | null;
  render_resolution: string | null;
  global_profile: null;
  games: Record<string, GameSettings>;
  game_filter: GameFilter;
}
export interface Bootstrap {
  settings: Settings;
  detected: string | null;
  devices: { id: string; name: string; native: string }[];
  resolutions: string[];
}
export type GameFilter = "verified" | "loadout" | "all";
export interface Game { appid: number; name: string; supported: boolean; verified: boolean; profile: Profile | null }
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
export const saveSettings = callable<[device: string, renderResolution: string], Settings>("save_settings");
export const setGameResolution = callable<[appid: number, resolution: string | null], Settings>("set_game_resolution");
export const setGameFilter = callable<[filter: GameFilter], Settings>("set_game_filter");
export const planProfile = callable<[appid: number, profile: Profile, current: string], Plan>("plan_profile");
export const applyProfile = callable<[appid: number, profile: Profile, current: string], ApplyResult>("apply_profile");

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
