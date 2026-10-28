import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  showModal,
  staticClasses,
  TextField,
  ToggleField,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { ReactNode, useEffect, useState } from "react";
import { FaSlidersH } from "react-icons/fa";
import * as api from "./api";


const profileLabel = (id: string | null) => api.PROFILES.find((p) => p.id === id)?.label ?? id;

// Cumulative filters: each one also shows what the previous one does.
const FILTERS: { id: api.GameFilter; label: string; keep: (g: api.Game) => boolean }[] = [
  { id: "verified", label: "Verified on this device", keep: (g) => g.verified },
  // Games with a Loadout entry, plus any game Loadout is managing (a profile applied, even generic).
  { id: "loadout", label: "All Loadout games", keep: (g) => g.supported || !!g.profile },
  { id: "all", label: "All games", keep: () => true },
];

// Hundreds of games (installed, or verified once the data grows) make a dropdown nobody can scroll
// with a D-pad: any filter's list is capped to the most recently played ones, plus a search.
const LIST_LIMIT = 50;
const RESET_LIST = 10;  // games named in the reset confirmation (all of them are reset)

function lastPlayed(appid: number): number {
  try {
    return window.appStore?.GetAppOverviewByAppID(appid)?.rt_last_time_played ?? 0;  // Steam internals
  } catch {
    return 0;
  }
}

const GREEN = "#59bf40";
const AMBER = "#e8a33d";

// Short status/warning lines between controls, with room to breathe above and below.
function Notice({ color, children }: { color: string; children: ReactNode }) {
  return <div style={{ fontSize: 12, color, padding: "8px 0" }}>{children}</div>;
}

// What a profile does on the selected game (the list's "(other devices)" / "(generic)" marks).
function gameNote(g: api.Game | undefined) {
  if (!g) return undefined;
  if (!g.supported) return "Generic: no Loadout settings for this game, profiles only set the FPS cap.";
  if (!g.verified) return "Other devices: Loadout has profiles for this game, not for this device yet.";
  return undefined;
}

function gameLabel(g: api.Game) {
  const kind = !g.supported ? " (generic)" : g.verified ? "" : " (other devices)";
  return `${g.name}${kind}${g.profile ? ` · ${profileLabel(g.profile)}` : ""}`;
}

// The QAM panel gets remounted (e.g. when a dropdown menu opens), which wipes useState: picks
// made in local state were lost. UI state lives at module level so it survives remounts, and
// every mounted copy re-renders on change (stale closures from a modal still update the UI).
const kept = new Map<string, unknown>();
const subscribers = new Set<() => void>();

function useKept<T>(key: string, initial: T): [T, (value: T) => void] {
  const [, rerender] = useState(0);
  useEffect(() => {
    const notify = () => rerender((n) => n + 1);
    subscribers.add(notify);
    return () => { subscribers.delete(notify); };
  }, []);
  return [(kept.has(key) ? kept.get(key) : initial) as T, (value: T) => setKept(key, value)];
}

function setKept(key: string, value: unknown) {
  kept.set(key, value);
  subscribers.forEach((notify) => notify());
}

type Status = { ok: boolean; text: string };

// Steam may play a toast's sound without showing it (e.g. while the Quick Access Menu is open),
// so every outcome is also written in the panel itself.
function report(ok: boolean, text: string) {
  setKept("status", { ok, text } satisfies Status);
  toaster.toast({ title: "Loadout", body: text, showToast: true });
}

const reportError = (e: unknown) => report(false, String(e));

function describe(plan: api.Plan, running: boolean) {
  const env = plan.changes.filter((c) => c.kind === "env");
  const args = plan.changes.filter((c) => c.kind === "arg");
  const launch = plan.changes.find((c) => c.kind === "launch_option");
  const fileKeys = plan.changes.filter((c) => c.kind === "file_key");
  return (
    <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
      {env.map((c) => <div key={c.key}>{c.key} = {c.new}</div>)}
      {args.map((c) => <div key={c.key}>Game argument: {c.key}</div>)}
      {fileKeys.length > 0 && <div style={{ marginTop: 8 }}>Game settings ({fileKeys[0].target.split("/").pop()}):</div>}
      {fileKeys.map((c) => <div key={c.target + c.key}>{c.key}: {c.old} → {c.new}</div>)}
      {launch ? (
        <>
          <div style={{ marginTop: 8 }}>Launch options before:</div>
          <code>{launch.old || "(empty)"}</code>
          <div style={{ marginTop: 8 }}>After:</div>
          <code>{launch.new || "(empty)"}</code>
        </>
      ) : <div>Nothing to change.</div>}
      {plan.warnings.map((w) => <div key={w} style={{ marginTop: 8, color: "#e8a33d" }}>{w}</div>)}
      {running && <div style={{ marginTop: 8, color: "#e8a33d" }}>Close the game first: it would overwrite its settings on exit.</div>}
      <div style={{ marginTop: 8 }}>Changes apply the next time the game is launched.</div>
    </div>
  );
}

function Onboarding({ boot, onDone }: { boot: api.Bootstrap; onDone: (s: api.Settings) => void }) {
  const [device, setDevice] = useKept("setup.device", boot.detected ?? "generic");
  const detectedName = boot.devices.find((d) => d.id === boot.detected)?.name;
  return (
    <PanelSection title="Setup">
      <PanelSectionRow>
        <div>{detectedName ? `Detected ${detectedName}. Is that right?` : "Device not detected, pick one:"}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem layout="below" label="Device" rgOptions={boot.devices.map((d) => ({ data: d.id, label: d.name }))}
          selectedOption={device} onChange={(o) => setDevice(o.data)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => api.saveSettings(device).then(onDone, reportError)}>
          Confirm
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
  const [boot, setBoot] = useKept<api.Bootstrap | undefined>("boot", undefined);
  const [settings, setSettings] = useKept<api.Settings | undefined>("settings", undefined);
  const [games, setGames] = useKept<api.Game[]>("games", []);
  const [appid, setAppid] = useKept<number | undefined>("appid", undefined);
  const [busy, setBusy] = useKept("busy", false);
  const [loadError, setLoadError] = useKept<string | undefined>("loadError", undefined);
  const [status] = useKept<Status | undefined>("status", undefined);
  // Remounts the cap switch and the device pick after a cancelled confirm, so they show the saved value again.
  const [pickTick, setPickTick] = useKept("pickTick", 0);
  const filter = FILTERS.find((f) => f.id === settings?.game_filter) ?? FILTERS[0];
  const [search, setSearch] = useKept("search", "");
  const inFilter = games.filter(filter.keep);
  // Search only when the list can be capped (a leftover query keeps it visible so it can be cleared).
  const searchable = inFilter.length > LIST_LIMIT || search !== "";
  const query = searchable ? search.trim().toLowerCase() : "";
  const candidates = query ? inFilter.filter((g) => g.name.toLowerCase().includes(query)) : inFilter;
  // Always listed when they match: a game with a profile applied, the running and the picked game.
  const running = window.SteamUIStore?.MainRunningAppID;
  const pinned = (g: api.Game) => !!g.profile || g.appid === appid || g.appid === running;
  const rest = candidates.filter((g) => !pinned(g));
  const cappedOut = Math.max(0, rest.length - LIST_LIMIT);
  const visible = cappedOut  // short lists stay alphabetical; long ones keep the most recently played
    ? [...candidates.filter(pinned), ...rest.sort((a, b) => lastPlayed(b.appid) - lastPlayed(a.appid)).slice(0, LIST_LIMIT)]
    : candidates;
  // Games with a profile applied that the filter hides: listed below, so Default stays reachable.
  const hiddenApplied = games.filter((g) => g.profile && !filter.keep(g));
  // Selection falls back to the first visible game when the current one is hidden.
  const selected = visible.some((g) => g.appid === appid) ? appid : visible[0]?.appid;

  useEffect(() => {
    // A backend that failed to start never answers, so don't wait forever.
    const timer = setTimeout(() => setLoadError("The Loadout backend did not respond."), 10000);
    api.getBootstrap().then(
      async (b) => {
        clearTimeout(timer);
        setBoot(b);
        setSettings(b.settings);
        const g = await api.listGames();
        setGames(g);
        // Which game to show: this session's pick, else the last game configured (survives Steam and
        // Decky restarts), else the running one; `selected` falls back to the first visible game.
        const installed = (id: unknown) => g.some((x) => x.appid === id);
        if (installed(kept.get("appid"))) return;
        const running = window.SteamUIStore?.MainRunningAppID;
        const next = [b.settings.last_game, running].find(installed);
        if (next !== undefined && next !== null) setAppid(next);
      },
      (e) => { clearTimeout(timer); setLoadError(String(e)); },
    ).catch(reportError);
  }, []);

  if (loadError && !boot) {
    return (
      <PanelSection>
        <PanelSectionRow>{loadError} Check the logs in ~/homebrew/logs/Loadout/.</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!boot || !settings) return <PanelSection><PanelSectionRow>Loading…</PanelSectionRow></PanelSection>;
  if (!settings.device) {
    // Games (verified on this device) and FPS caps were loaded without a device: reload them for it.
    const done = async (s: api.Settings) => {
      setSettings(s);
      setKept("status", undefined);
      setBoot(await api.getBootstrap());
      setGames(await api.listGames());
    };
    return <Onboarding boot={boot} onDone={(s) => done(s).catch(reportError)} />;
  }

  const game = selected !== undefined ? settings.games[String(selected)] : undefined;
  const info = games.find((g) => g.appid === selected);
  const current: api.Profile = game?.profile ?? "default";
  const fpsCap = game?.fps_cap ?? true;
  const currentCap = boot.fps_limits?.[current];
  const profileDevice = game?.profile_device ?? null;
  const deviceName = (id: string) => boot.devices.find((d) => d.id === id)?.name ?? id;

  const pick = async (profile: api.Profile, cap = fpsCap, from = profileDevice) => {
    if (selected === undefined || busy) return;
    setBusy(true);
    try {
      const before = await api.getLaunchOptions(selected);
      const plan = await api.planProfile(selected, profile, before, cap, from);
      // Game config files are never written while the game runs (many games rewrite them on exit).
      const running = plan.file_writes.length > 0 && window.SteamUIStore?.MainRunningAppID === selected;
      showModal(
        <ConfirmModal
          strTitle={`Apply ${api.PROFILES.find((p) => p.id === profile)?.label}?`}
          strDescription={describe(plan, running)}
          bOKDisabled={plan.blocked || running}
          onCancel={() => setPickTick(pickTick + 1)}
          onOK={async () => {
            try {
              // Re-read: the user may have edited launch options while the dialog was open.
              const result = await api.applyProfile(selected, profile, await api.getLaunchOptions(selected), cap, from);
              if (!result.applied) {
                reportError(result.warnings.join(" "));
                return;
              }
              api.setLaunchOptions(selected, result.launch_options);
              setSettings((await api.getBootstrap()).settings);
              setGames(await api.listGames());  // refresh the applied profile shown next to each game
              report(true, profile === "default"
                ? `${info?.name}: original settings restored.`
                : `${profileLabel(profile)} applied to ${info?.name}. Takes effect the next time it launches.`);
            } catch (e) {
              reportError(e);
            }
          }}
        />,
      );
    } catch (e) {
      reportError(e);
    } finally {
      setBusy(false);
    }
  };

  // Default on every game with a profile, then back to Setup. Stops (settings kept) at the first
  // game that can't be restored, so nothing is left half-reset without the user knowing.
  const reset = () => {
    const applied = games.filter((g) => g.profile);
    const open = applied.find((g) => g.appid === window.SteamUIStore?.MainRunningAppID);
    // Only the most recently played are named: a long list would push the buttons off screen.
    const named = [...applied].sort((a, b) => lastPlayed(b.appid) - lastPlayed(a.appid)).slice(0, RESET_LIST);
    const more = applied.length - named.length;
    showModal(
      <ConfirmModal
        strTitle="Reset Loadout?"
        strDescription={
          <div>
            {applied.length > 0
              ? <div>These games go back to Default (original), their launch options and the game settings
                  Loadout changed: {named.map((g) => `${g.name} (${profileLabel(g.profile)})`).join(", ")}
                  {more > 0 ? `, and ${more} more` : ""}.</div>
              : <div>No game has a profile applied.</div>}
            <div style={{ marginTop: 8 }}>Then all Loadout settings are cleared and Setup asks for your device again.</div>
            {open && <div style={{ marginTop: 8, color: AMBER }}>Close {open.name} first: it would overwrite its settings on exit.</div>}
          </div>
        }
        bOKDisabled={!!open}
        strOKButtonText="Reset"
        onOK={async () => {
          setBusy(true);
          try {
            for (const [i, g] of applied.entries()) {
              // In the panel's status line, so a long reset doesn't look frozen (no toast per game).
              setKept("status", { ok: true, text: `Resetting ${i + 1} of ${applied.length}: ${g.name}…` } satisfies Status);
              const s = settings.games[String(g.appid)];
              const result = await api.applyProfile(g.appid, "default", await api.getLaunchOptions(g.appid),
                s?.fps_cap ?? true, s?.profile_device ?? null);
              if (!result.applied) {
                reportError(`${g.name}: ${result.warnings.join(" ")} Nothing else was reset.`);
                return;
              }
              api.setLaunchOptions(g.appid, result.launch_options);
            }
            setSettings(await api.resetSettings());
            setBoot(await api.getBootstrap());
            setAppid(undefined);
            report(true, "Loadout reset. Pick your device to start again.");
          } catch (e) {
            reportError(e);
          } finally {
            setBusy(false);
          }
        }}
      />,
    );
  };

  // Picked once in Setup: another device's profiles are borrowed per game ("Use profiles from"), so
  // it's shown, not switched; Reset Loadout redoes Setup.
  return (
    <>
      <PanelSection title="Game">
        <PanelSectionRow>
          <Field label="Device">{deviceName(settings.device)}</Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem layout="below" label="Show" rgOptions={FILTERS.map((f) => ({ data: f.id, label: f.label }))}
            selectedOption={filter.id}
            onChange={(o) => api.setGameFilter(o.data).then(setSettings, reportError)} />
        </PanelSectionRow>
        {searchable && (
          <PanelSectionRow>
            <TextField label="Search games" placeholder="Type part of a name" bShowClearAction
              value={search} onChange={(e) => setSearch(e.target.value)} />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <DropdownItem layout="below" label="Game" disabled={!visible.length} description={gameNote(info)}
            strDefaultLabel={query ? "No games match the search" : "No games for this filter"}
            rgOptions={visible.map((g) => ({ data: g.appid, label: gameLabel(g) }))}
            selectedOption={selected} onChange={(o) => { setAppid(o.data); setKept("status", undefined); }} />
        </PanelSectionRow>
        {cappedOut > 0 && (
          <PanelSectionRow>
            <Notice color={AMBER}>
              {query
                ? `Showing ${LIST_LIMIT} of ${LIST_LIMIT + cappedOut} matches. Type more of the name to narrow it down.`
                : `Lots of games match this filter, so only the ${LIST_LIMIT} most recently played are listed ` +
                  `(${cappedOut} more). Use the search to find any other game.`}
            </Notice>
          </PanelSectionRow>
        )}
        {hiddenApplied.length > 0 && (
          <PanelSectionRow>
            <Notice color={AMBER}>
              Profiles applied to hidden games:{" "}
              {hiddenApplied.map((g) => `${g.name} (${profileLabel(g.profile)})`).join(", ")}.
              Show "All games" to change them.
            </Notice>
          </PanelSectionRow>
        )}
        {/* No profiles for this device: borrow another device's (e.g. one with a similar chip).
            Picking re-applies the current profile, confirmed like the cap switch. */}
        {info?.supported && !info.verified && (
          <PanelSectionRow>
            <DropdownItem key={pickTick} layout="below" label="Use profiles from" disabled={busy}
              description="No Loadout profiles for your device yet. Pick a device with a similar chip."
              rgOptions={[{ data: null, label: "None (FPS cap only)" },
                ...info.devices.map((d) => ({ data: d, label: deviceName(d) }))]}
              selectedOption={info.devices.includes(profileDevice ?? "") ? profileDevice : null}
              onChange={(o) => pick(current, fpsCap, o.data)} />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <DropdownItem layout="below" label="Profile" disabled={selected === undefined || busy}
            rgOptions={api.PROFILES.map((p) => ({ data: p.id, label: p.label }))}
            selectedOption={current} onChange={(o) => pick(o.data)} />
        </PanelSectionRow>
        {/* Off: cap with Steam's own limiter in the QAM, changeable without leaving the game.
            Switching re-applies the current profile (confirmed like any apply; cancel keeps it). */}
        {currentCap && (
          <PanelSectionRow>
            <ToggleField key={pickTick} label={`Apply the profile's ${currentCap} FPS cap`} checked={fpsCap}
              disabled={busy}
              description="On: keep Steam's frame limit off. Off: set it in the Quick Access Menu."
              onChange={(on) => pick(current, on)} />
          </PanelSectionRow>
        )}
        {status && (
          <PanelSectionRow>
            <Notice color={status.ok ? GREEN : AMBER}>
              {status.ok ? "✓ " : "⚠ "}{status.text}
            </Notice>
          </PanelSectionRow>
        )}
      </PanelSection>
      <PanelSection title="Settings">
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={reset}
            description="Every game back to Default (original), then Setup again.">
            Reset Loadout
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => ({
  name: "Loadout",
  titleView: <div className={staticClasses.Title}>Loadout</div>,
  content: <Content />,
  icon: <FaSlidersH />,
}));
