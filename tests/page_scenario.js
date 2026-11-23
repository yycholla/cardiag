// Drives the page's script the way a person would. DATA holds real responses
// captured from the server; the page script has already run above this file.

function check(condition, message) {
  if (!condition) throw new Error("check failed: " + message);
}

const text = (node) => node.textContent;

async function settle() {
  for (let i = 0; i < 20; i++) await null;
}

function feed(payload) {
  streams[0].onmessage({ data: JSON.stringify(payload) });
}

async function scenario() {
  const live = DATA.live;
  routes["/api/values"] = DATA.values;
  routes["/api/codes"] = DATA.codes;
  routes["/api/monitors"] = DATA.monitors;
  routes["/api/sessions"] = DATA.sessions;

  check(streams.length === 1 && streams[0].url === "/api/stream", "opens the live stream once");

  // First update from a connected car.
  feed(live[0]);
  await settle();
  check(text($("link-text")) === "Connected", "shows connected, got " + text($("link-text")));
  check(text($("link-detail")).includes("VIN 1FADP3F2XHL123456"), "shows the VIN");
  check(text($("link-detail")).includes("Engine (7E8), Transmission (7E9)"), "shows the modules");
  check($("link-icon").getAttribute("class") === "icon good", "good status icon");
  check($("tiles").children.length === live[0].readings.length, "one tile per reading");
  check(text($("tiles").children[0]).includes("Engine speed"), "first tile is engine speed");
  check($("live-empty").hidden === true, "hides the waiting message");
  check($("record").disabled === false, "recording is allowed once connected");

  // The value chooser is filled in on connect.
  check(calls.some((call) => call.path === "/api/values"), "asks which values the car offers");
  const boxes = $("chooser-list").children.map((row) => row.children[0]);
  check(boxes.length === DATA.values.available.length, "one checkbox per offered value");
  check(boxes.filter((box) => box.checked).length === DATA.values.watched.length, "watched values are ticked");

  // More updates build the trend line.
  for (const payload of live.slice(1)) feed(payload);
  const rpm = tiles.get("01:0C");
  const lastRpm = live[live.length - 1].readings[0].value;
  check(rpm.history.length === live.length, "keeps every update in the history");
  check(text(rpm.num) === fmt(lastRpm), "shows the latest value, got " + text(rpm.num));
  const path = rpm.trend.getAttribute("d");
  check(/^M[\d.]+ [\d.]+( L[\d.]+ [\d.]+)+$/.test(path), "trend path is well formed: " + path);
  check(path.split(" L").length === live.length, "trend has one point per update");
  check(/^M[\d.]+ [\d.]+h0\.01$/.test(rpm.dot.getAttribute("d")), "latest-point dot: " + rpm.dot.getAttribute("d"));
  check(/ to .+ over \d+ s$/.test(text(rpm.caption)), "range caption: " + text(rpm.caption));
  check(rpm.cross.getAttribute("visibility") === "hidden", "no crosshair until hovered");
  check(!path.includes("NaN") && !text(rpm.caption).includes("NaN"), "no NaN anywhere");

  // Hovering the trend line reads off a past value.
  const chart = $("tiles").children[0].children.find((child) => child.tag === "svg");
  check(chart, "numeric tiles have a trend chart");
  await chart.fire("pointermove", { clientX: 0 });
  check(rpm.cross.getAttribute("visibility") === "visible", "crosshair appears on hover");
  check(text(rpm.caption).startsWith(fmt(rpm.history[0].value) + " rpm, "), "left edge is the oldest value: " + text(rpm.caption));
  check(text(rpm.caption).endsWith(" ago"), "hover caption says how long ago");
  await chart.fire("pointermove", { clientX: 5000 });
  check(text(rpm.caption).startsWith(fmt(lastRpm) + " rpm, 0 s ago"), "right edge is the newest value: " + text(rpm.caption));
  await chart.fire("pointerleave");
  check(rpm.cross.getAttribute("visibility") === "hidden", "crosshair goes away");

  // Values that are words get no chart.
  const words = buildTile({ key: "01:03", name: "Fuel system status", value: "closed loop", unit: "" });
  words.history.push({ t: 0, value: "closed loop" });
  drawTile(words);
  check(!words.root.children.some((child) => child.tag === "svg"), "no trend chart for words");
  check(text(words.num) === "closed loop", "shows the words");

  // Number formatting.
  check(fmt(812.25) === "812" && fmt(12.5) === "12.5" && fmt(4.062) === "4.06" && fmt(20) === "20", "number formatting");
  check(fmtDuration(42.4) === "42 s" && fmtDuration(75) === "1 min 15 s" && fmtDuration(3725) === "1 h 2 min", "durations");

  // Unticking a value saves the new selection.
  boxes[0].checked = !boxes[0].checked;
  routes["/api/watch"] = DATA.values;
  await boxes[0].fire("change");
  const saved = calls.filter((call) => call.path === "/api/watch").pop();
  check(saved && saved.options.method === "POST", "posts the new selection");
  check(JSON.parse(saved.options.body).pids.length === boxes.filter((box) => box.checked).length, "sends the ticked values");

  // Codes.
  await $("read-codes").fire("click");
  let codes = text($("codes"));
  for (const expected of ["Check-engine light is on", "Engine (7E8)", "Transmission (7E9)", "P0171", "P0456",
    "P0902", "None", "Freeze frame for P0171", "Engine speed" + fmt(1850) + " rpm"]) {
    check(codes.includes(expected), "codes panel shows " + expected + " in: " + codes);
  }
  routes["/api/codes"] = {
    mil_on: null,
    modules: [{ label: "Engine (10)", stored: ["P0300"], pending: [], permanent: null }],
    freeze_frame: null,
  };
  await $("read-codes").fire("click");
  codes = text($("codes"));
  check(codes.includes("Not reported by this module"), "marks a kind the module did not answer");
  check(!codes.includes("Check-engine light") && !codes.includes("Freeze frame"), "omits what the car did not report");
  routes["/api/codes"] = { error: "the vehicle stopped answering" };
  await $("read-codes").fire("click");
  check(text($("codes")).includes("the vehicle stopped answering"), "shows the server's error");

  // Readiness.
  await $("read-monitors").fire("click");
  const monitors = text($("monitors"));
  for (const expected of ["Engine (7E8)", "Check-engine light on, 1 code stored, spark ignition",
    "Evaporative system!Not complete", "Catalyst✓Complete"]) {
    check(monitors.includes(expected), "readiness panel shows " + expected + " in: " + monitors);
  }

  // Tabs and recordings.
  await $("tab-sessions").fire("click");
  await settle();
  check($("panel-sessions").hidden === false && $("panel-live").hidden === true, "switches panels");
  check($("tab-sessions").getAttribute("aria-selected") === "true", "marks the chosen tab");
  check($("tab-live").getAttribute("aria-selected") === "false", "unmarks the other tabs");
  check(text($("sessions")).includes("Recording 1: idle check"), "lists the recording: " + text($("sessions")));
  const download = $("sessions").descendants().find((node) => node.tag === "a");
  check(download.getAttribute("href") === "/api/sessions/1.csv", "links to the CSV");
  routes["/api/sessions"] = [];
  await $("tab-sessions").fire("click");
  await settle();
  check(text($("sessions")).includes("No recordings yet"), "explains an empty list");

  // Starting and stopping a recording.
  const recordRequests = [];
  routes["/api/record"] = (options) => {
    const request = JSON.parse(options.body);
    recordRequests.push(request);
    return request.action === "start" ? DATA.recording : live[0].status;
  };
  $("note").value = "cold start";
  await $("record").fire("click");
  check(recordRequests[0].action === "start" && recordRequests[0].note === "cold start", "sends the note");
  check(text($("record")) === "Stop recording", "button turns into stop");
  check(text($("record-status")).startsWith("Recording 1 · "), "shows the running recording: " + text($("record-status")));
  check($("note").hidden === true && $("note").value === "", "hides and clears the note box");
  await $("record").fire("click");
  check(recordRequests[1].action === "stop", "second press stops");
  check(text($("record")) === "Start recording" && text($("record-status")) === "", "back to idle");

  // Settings: switching to a simulated car and back.
  routes["/api/network"] = DATA.network;
  routes["/api/update"] = DATA.update;
  await $("tab-settings").fire("click");
  await settle();
  check(text($("source-state")).includes("Using the real car, through the adapter"), "says the car is real");
  const sourceLabels = () => $("sources").children.map(text).join("|");
  check(sourceLabels() === "Simulate a Ford Focus|Simulate a Chevrolet Tahoe", "offers the simulated cars: " + sourceLabels());
  const simRequests = [];
  routes["/api/simulation"] = (options) => {
    simRequests.push(JSON.parse(options.body));
    return simRequests.length === 1 ? DATA.simulating : { error: "no such car" };
  };
  await $("sources").children[1].fire("click");
  await settle();
  check(simRequests[0].vehicle === "tahoe", "asks for the Tahoe");
  check(DATA.simulating.state === "starting" && text($("link-text")) === "Starting", "shows the switch under way");
  check($("tiles").children.length === 0, "the real car's values are cleared at once");
  feed(DATA.tahoe);
  await settle();
  check(text($("link-text")) === "Simulation", "the header says it is a simulation, got " + text($("link-text")));
  check(text($("link-detail")).startsWith("Simulated Chevrolet Tahoe, made-up data · VIN "), "and which car: " + text($("link-detail")));
  check(text($("source-state")).includes("simulated Chevrolet Tahoe, not a real car"), "settings say so too");
  check(sourceLabels() === "Use the real car|Simulate a Ford Focus", "offers the way back: " + sourceLabels());
  check($("tiles").children.length === DATA.tahoe.readings.length, "shows the Tahoe's values");
  await $("sources").children[0].fire("click");
  check(simRequests[1].vehicle === null, "asks for the real car");
  check(text($("source-state")).includes("no such car"), "shows why a switch failed");
  feed(live[0]);
  await settle();
  check(text($("link-text")) === "Connected" && sourceLabels().startsWith("Simulate a Ford Focus"), "back on the real car");
  check(tiles.has("01:0C") && tiles.get("01:0C").history.length === 1, "trend lines start again after a switch");

  // Settings: Wi-Fi. Nothing saved yet, so the form is offered.
  check($("wifi-card").hidden === false, "shows Wi-Fi where the app manages it");
  check(text($("wifi-state")).includes("Hotspot cardiag is on"), "hotspot state: " + text($("wifi-state")));
  check($("wifi-form").hidden === false && $("wifi-saved").hidden === true, "offers to save a network");
  routes["/api/network/scan"] = DATA.scan;
  await $("wifi-scan").fire("click");
  const found = $("wifi-networks").children;
  check(text(found[0]) === "Home · signal 82%", "lists networks: " + text(found[0]));
  check(text(found[2]) === "Cafe: Free · signal 40% · open", "marks open networks: " + text(found[2]));
  await found[0].fire("click");
  check($("wifi-ssid").value === "Home", "picking a network fills in its name");

  let networkNow = DATA.network;
  const networkRequests = [];
  const networkAnswers = { save: DATA.network_saved, join: DATA.network_joining, hotspot: DATA.network_leaving };
  routes["/api/network"] = (options) => {
    if (!options.method) return networkNow;
    const request = JSON.parse(options.body);
    networkRequests.push(request);
    return networkAnswers[request.action];
  };
  $("wifi-password").value = "short";
  networkAnswers.save = { error: "a Wi-Fi password is 8 to 63 characters" };
  await $("wifi-save").fire("click");
  check(text($("wifi-note")) === "a Wi-Fi password is 8 to 63 characters", "explains a refused password");
  check($("wifi-password").value === "short", "and leaves it there to correct");
  $("wifi-password").value = "correct horse";
  networkAnswers.save = DATA.network_saved;
  await $("wifi-save").fire("click");
  const sent = networkRequests[networkRequests.length - 1];
  check(sent.action === "save" && sent.ssid === "Home" && sent.password === "correct horse", "sends the name and password");
  check($("wifi-password").value === "", "clears the password box");
  check($("wifi-saved").hidden === false && $("wifi-form").hidden === true, "shows the saved network instead of the form");
  check(text($("wifi-join")) === "Join Home" && $("wifi-join").hidden === false, "offers to join it");
  check($("wifi-hotspot").hidden === true, "no need for 'back to the hotspot' yet");
  check(text($("wifi-state")).includes("Hotspot cardiag is on"), "saving does not leave the hotspot");

  await $("wifi-join").fire("click");
  check(text($("wifi-state")).includes("Switching to Home…"), "says it is switching: " + text($("wifi-state")));
  check($("wifi-join").disabled === true && $("wifi-forget").disabled === true, "no second press while switching");
  const address = "http://" + DATA.network.hostname + ".local:8000";
  check(text($("wifi-note")).includes("Put this device on Home and open " + address), "says where to find the page next: " + text($("wifi-note")));
  check(text($("wifi-note")).includes("the hotspot comes back"), "and what happens if joining fails");
  check(timers.length === 1, "keeps watching while the radio changes over");
  networkNow = DATA.network_joined;
  timers.shift()();
  await settle();
  check(text($("wifi-state")).includes("On Wi-Fi network Home, address 192.168.0.23"), "joined: " + text($("wifi-state")));
  check($("wifi-join").hidden === true && $("wifi-hotspot").hidden === false, "now offers the way back");
  check($("wifi-hotspot").disabled === false && timers.length === 0, "settled, so it stops asking");
  await $("wifi-hotspot").fire("click");
  check(networkRequests[networkRequests.length - 1].action === "hotspot", "asks for the hotspot");
  check(text($("wifi-note")).includes("Put this device on the cardiag hotspot and open " + address), "hotspot directions: " + text($("wifi-note")));
  timers.length = 0;

  networkNow = Object.assign({}, DATA.network_saved, { problem: "Could not join Home: the password was not accepted. The hotspot is back on." });
  await loadNetwork();
  check(text($("wifi-state")).includes("the password was not accepted"), "shows why joining failed");
  check(text($("wifi-state")).includes("Hotspot cardiag is on"), "alongside where the box is now");
  networkNow = { error: "NetworkManager is not running" };
  await loadNetwork();
  check(text($("wifi-state")).includes("NetworkManager is not running"), "shows a Wi-Fi failure");
  networkNow = { managed: false };
  await loadNetwork();
  check($("wifi-card").hidden === true, "no Wi-Fi card where the app does not manage Wi-Fi");

  // Settings: software updates.
  check(text($("update-version")) === "Version " + DATA.update.current && text($("update-state")) === "", "shows the version: " + text($("update-version")));
  check($("update-check").hidden === false && $("update-install").hidden === true, "offers to check, not yet to install");
  const updateAnswers = { check: { error: "could not reach GitHub. Updates need internet access, so join a Wi-Fi network first" } };
  routes["/api/update"] = (options) => (options.method ? updateAnswers[JSON.parse(options.body).action] : DATA.update);
  await $("update-check").fire("click");
  check(text($("update-state")).includes("join a Wi-Fi network first"), "explains a failed check");
  updateAnswers.check = Object.assign({}, DATA.update_found, { available: false, latest: DATA.update.current, notes: "" });
  await $("update-check").fire("click");
  check(text($("update-state")).includes("This is the latest version"), "says when there is nothing newer");
  check($("update-install").hidden === true, "and offers nothing to install");
  updateAnswers.check = DATA.update_found;
  await $("update-check").fire("click");
  check(text($("update-state")).includes("Version 9.0.0 is available") && text($("update-version")) === "Version " + DATA.update.current, "announces the update");
  check(text($("update-notes")) === "Reads more codes.", "with its notes");
  check($("update-install").hidden === false, "and offers to install it");
  updateAnswers.install = { error: "version 9.0.0 failed its self-test here, so it was not installed" };
  await $("update-install").fire("click");
  check(text($("update-state")).includes("failed its self-test"), "explains a failed install");
  check($("update-install").hidden === false && $("update-install").disabled === false, "and lets it be tried again");
  updateAnswers.install = DATA.update_installed;
  await $("update-install").fire("click");
  check(text($("update-state")).includes("Version 9.0.0 is installed"), "confirms the install: " + text($("update-state")));
  check($("update-install").hidden === true && reloads === 0, "nothing more to install; not reloaded yet");
  feed(Object.assign({}, live[0], { status: Object.assign({}, live[0].status, { version: "9.0.0" }) }));
  check(reloads === 1, "reloads once the new version is the one answering");
  routes["/api/update"] = Object.assign({}, DATA.update, { rolled_back: "9.0.0" });
  await loadUpdate();
  check(text($("update-state")).includes("Version 9.0.0 did not start, so the box went back to version " + DATA.update.current), "reports an undone update");
  routes["/api/update"] = { managed: false, current: DATA.update.current };
  await loadUpdate();
  check($("update-check").hidden === true && text($("update-version")) === "Version " + DATA.update.current && text($("update-state")) === "", "version only, where updates are not managed");

  // A value that stops arriving keeps its tile briefly, then goes.
  const without = Object.assign({}, live[0], { readings: live[0].readings.slice(1) });
  feed(without);
  check(tiles.has("01:0C"), "tile survives one missed update");
  for (let i = 0; i < MISSED_LIMIT; i++) feed(without);
  check(!tiles.has("01:0C"), "tile is removed once the value stays away");
  check($("tiles").children.length === without.readings.length, "grid matches the remaining values");

  // The car is switched off.
  const off = Object.assign({}, live[0].status, {
    state: "no_vehicle", message: "turn the ignition on", vin: null, modules: [], recording: null,
  });
  feed({ status: off, elapsed: 0, readings: [] });
  check(text($("link-text")) === "Waiting for the car", "says it is waiting for the car");
  check(text($("link-detail")) === "turn the ignition on", "passes on the reason");
  check($("link-icon").getAttribute("class") === "icon warning", "warning status icon");
  check($("tiles").children.length === 0 && $("live-empty").hidden === false, "clears stale values");
  check($("record").disabled === true, "recording is not offered without a car");

  // The server itself goes away.
  streams[0].onerror();
  check(text($("link-text")) === "App not reachable", "says the app is unreachable");
  fetchFails = true;
  await $("read-codes").fire("click");
  check(text($("codes")).includes("Could not reach the app"), "explains a failed request");
}

scenario().then(
  () => console.log("PAGE-OK"),
  (error) => console.log("PAGE-FAIL " + ((error && error.message) || error) + "\n" + ((error && error.stack) || "")),
);
