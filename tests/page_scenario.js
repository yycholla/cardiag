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
  routes["/api/central"] = DATA.central;
  await $("tab-settings").fire("click");
  await settle();
  check(text($("source-state")).includes("Using the real car, through the adapter"), "says the car is real");
  const sourceLabels = () => $("sources").children.map(text).join("|");
  check(sourceLabels() === "Simulate a Ford Focus|Simulate a Ford Focus with a slipping clutch|Simulate a Chevrolet Tahoe", "offers the simulated cars: " + sourceLabels());
  const simRequests = [];
  routes["/api/simulation"] = (options) => {
    simRequests.push(JSON.parse(options.body));
    return simRequests.length === 1 ? DATA.simulating : { error: "no such car" };
  };
  await $("sources").children[2].fire("click");
  await settle();
  check(simRequests[0].vehicle === "tahoe", "asks for the Tahoe");
  check(DATA.simulating.state === "starting" && text($("link-text")) === "Starting", "shows the switch under way");
  check($("tiles").children.length === 0, "the real car's values are cleared at once");
  check(text($("codes")) === "" && text($("monitors")) === "", "and so are its codes and readiness");
  feed(DATA.tahoe);
  await settle();
  check(text($("link-text")) === "Simulation", "the header says it is a simulation, got " + text($("link-text")));
  check(text($("link-detail")).startsWith("Simulated Chevrolet Tahoe, made-up data · VIN "), "and which car: " + text($("link-detail")));
  check(text($("source-state")).includes("simulated Chevrolet Tahoe, not a real car"), "settings say so too");
  check(sourceLabels() === "Use the real car|Simulate a Ford Focus|Simulate a Ford Focus with a slipping clutch", "offers the way back: " + sourceLabels());
  check($("tiles").children.length === DATA.tahoe.readings.length, "shows the Tahoe's values");
  await $("sources").children[0].fire("click");
  check(simRequests[1].vehicle === null, "asks for the real car");
  check(text($("source-state")).includes("no such car"), "shows why a switch failed");
  // Codes and readiness asked of the simulated car, with the answers arriving after the switch back.
  routes["/api/codes"] = () => {
    feed(live[0]);
    return DATA.codes;
  };
  await $("read-codes").fire("click");
  check(text($("codes")) === "", "a late answer about the simulated car is not shown for the real one: " + text($("codes")));
  routes["/api/codes"] = DATA.codes;
  routes["/api/monitors"] = () => {
    feed(DATA.tahoe);
    return DATA.monitors;
  };
  await $("read-monitors").fire("click");
  check(text($("monitors")) === "", "nor a late readiness answer: " + text($("monitors")));
  routes["/api/monitors"] = DATA.monitors;
  await $("read-codes").fire("click");
  check(text($("codes")).includes("P0171"), "codes read after the switch are shown");
  feed(live[0]);
  await settle();
  check(text($("codes")) === "", "and cleared again when the car changes");
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

  // Settings: the central server and the travelling hotspot.
  check($("central-card").hidden === false && text($("central-state")).includes("Recordings stay on this box"), "central server card: " + text($("central-state")));
  const centralRequests = [];
  routes["/api/central"] = (options) => {
    if (!options.method) return DATA.central;
    centralRequests.push(JSON.parse(options.body));
    return Object.assign({}, DATA.central, { url: "http://cardiag-home:8000", waiting: 2, problem: "could not reach the central server; recordings are kept here and sent when it answers" });
  };
  $("central-url").value = "cardiag-home:8000";
  await $("central-save").fire("click");
  check(centralRequests[0].url === "cardiag-home:8000", "sends the address as typed");
  check(text($("central-state")).includes("Could not reach the central server") && text($("central-state")).includes("2 recordings are waiting"), "says what is waiting and why: " + text($("central-state")));
  check($("central-url").value === "http://cardiag-home:8000" && $("central-send").hidden === false, "shows the tidied address and offers to send");
  showNetwork(DATA.network_uplink);
  check($("uplink-saved").hidden === false && $("uplink-form").hidden === true, "shows the saved travelling hotspot");
  check(text($("uplink-state")).includes("Saved: iPad. The box joins it by itself"), "and that it is joined automatically: " + text($("uplink-state")));
  check($("wifi-hotspot").hidden === true && $("uplink-join").hidden === false, "offers to join it now");
  showNetwork(Object.assign({}, DATA.network_uplink, { mode: "uplink", address: "172.20.10.4" }));
  check(text($("wifi-state")).includes("On the travelling hotspot iPad, address 172.20.10.4"), "joined to it: " + text($("wifi-state")));
  check($("wifi-hotspot").hidden === false && $("uplink-join").hidden === true, "now offers the way back to the own hotspot");

  // Settings: the polling rate.
  feed(Object.assign({}, live[0], { status: Object.assign({}, live[0].status, { rate: 3.8, values: 12 }) }));
  check(text($("interval-state")) === "Reading 12 values 3.80 times a second", "says what is being achieved: " + text($("interval-state")));
  check($("interval").value === String(live[0].status.interval) && $("interval").children.length === 8, "lists the rates, with the one in use even when it is unusual");
  const intervalRequests = [];
  routes["/api/interval"] = (options) => {
    intervalRequests.push(JSON.parse(options.body));
    return intervalRequests.length === 1 ? { error: "the time between updates must be between 0 and 10 seconds" }
      : Object.assign({}, live[0].status, { interval: 1 });
  };
  $("interval").value = "0.5";
  await $("interval").fire("change");
  check(text($("interval-note")).startsWith("The time between updates must be"), "explains a refused rate");
  check($("interval").value === String(live[0].status.interval), "and shows what the app is still doing");
  $("interval").value = "1";
  await $("interval").fire("change");
  check(intervalRequests[1].seconds === 1 && $("interval").value === "1" && $("interval").children.length === 7, "a chosen rate is sent and shown");
  check(text($("interval-note")) === "", "with nothing to complain about");

  // Diagnosis, from the server's analysis of the live car.
  const sane = (node, what) => {
    const words = text(node);
    check(!words.includes("NaN") && !words.includes("undefined") && !words.includes("null"), what + " has no stray values: " + words);
    const bad = node.descendants().filter((item) => item.tag === "path" && /NaN|undefined/.test(String(item.getAttribute("d"))));
    check(bad.length === 0, what + " draws every line");
  };
  routes["/api/sessions"] = DATA.sessions_after;
  routes["/api/analysis?source=live"] = DATA.analysis_live;
  await $("tab-diagnosis").fire("click");
  await settle();
  check($("report-bar").hidden === false && $("panel-diagnosis").hidden === false, "shows the report bar with the Diagnosis tab");
  check($("report-source").children.length === DATA.sessions_after.length + 1 && $("report-source").value === "live", "offers live and every recording");
  const diagnosis = text($("diagnosis"));
  for (const expected of ["Against the healthy band", "Long-term fuel trim", "Above band", "General guide",
    "Fuel trim by operating region", "Air flow check", "Warm-up", "Where the engine has been", "Fuel used, estimated"]) {
    check(diagnosis.includes(expected), "diagnosis shows " + expected);
  }
  sane($("diagnosis"), "diagnosis");
  check(/ updates$/.test(text($("report-note"))), "says how much it is looking at: " + text($("report-note")));

  // Drive, from a recording of a geared car with a slipping third gear.
  const drivePath = "/api/analysis?source=" + DATA.drive_id + "&against=" + DATA.drive_id;
  routes[drivePath] = DATA.analysis_drive;
  await $("tab-drive").fire("click");
  await settle();
  check($("panel-drive").hidden === false && $("report-bar").hidden === false, "the report bar stays for the Drive tab");
  $("report-source").value = String(DATA.drive_id);
  $("report-against").value = String(DATA.drive_id);
  await $("report-source").fire("change");
  const drive = text($("drive"));
  check(!drive.includes("From the modules themselves"), "no maker-specific card when none are set up");
  for (const expected of ["Gear map", "the 6 gears learned", "Gear over time", "Shifts", "2 to 3", "Flare", "Slip by gear",
    "Slip under load in gear 3", "odd-gear clutch", "Pulling power", "Pedal", "No slower", "What this cannot see"]) {
    check(drive.includes(expected), "drive shows " + expected);
  }
  sane($("drive"), "drive");
  check(/Shift 2 to 3 at /.test(drive), "opens the worst shift first");
  const buttons = () => $("drive").descendants().filter((node) => node.tag === "button");
  check(buttons().filter((node) => text(node) === "Open").length < DATA.analysis_drive.drive.shifts.length, "a long list starts with only the shifts that were not clean");
  await buttons().find((node) => text(node).startsWith("List all ")).fire("click");
  check(buttons().filter((node) => text(node) === "Open").length === DATA.analysis_drive.drive.shifts.length, "and can be opened out in full");
  await buttons().find((node) => text(node) === "Open").fire("click");
  check(/Shift 1 to 2 at /.test(text($("drive"))), "another shift can be opened");
  routes[drivePath] = { error: "there is no recording 2" };
  await $("report-refresh").fire("click");
  check(text($("report-note")) === "there is no recording 2" && text($("drive")) === "", "a failed report says why and shows nothing stale");

  // A drive capture watches fewer values, records, then puts things back.
  routes["/api/setup"] = DATA.setup;
  const watchRequests = [];
  routes["/api/watch"] = (options) => {
    watchRequests.push(JSON.parse(options.body).pids);
    return DATA.values;
  };
  routes["/api/analysis?source=1"] = DATA.analysis_live;
  await $("capture").fire("click");
  check(JSON.stringify(watchRequests[0]) === JSON.stringify(DATA.setup.drive_pids), "watches only what shifting needs");
  check(text($("capture")) === "Stop the drive capture" && text($("capture-note")).startsWith("Recording 1."), "capture is running: " + text($("capture-note")));
  $("report-against").value = "";
  await $("capture").fire("click");
  await settle();
  check(JSON.stringify(watchRequests[1]) === JSON.stringify(DATA.values.watched), "puts the watched values back");
  check(text($("capture")) === "Start a drive capture" && $("report-source").value === "1", "and shows the recording it made");

  // Setup.
  await $("tab-setup").fire("click");
  await settle();
  check($("setup-steps").hidden === false && $("setup-empty").hidden === true, "shows the steps for a connected car");
  check(text($("setup-car")).includes("1FADP3F2XHL123456"), "names the car");
  const offers = text($("setup-offers"));
  check(offers.includes("Engine (7E8): 20 values") && offers.includes("Transmission (7E9): 1 value"), "lists what each module offers: " + offers.slice(0, 80));
  check(offers.includes("Accelerator pedal position") && offers.includes("Not offered") && offers.includes("throttle position instead"), "and what is missing");
  check(text($("setup-summary")).includes("Needs the engine size") && text($("setup-summary")).includes("Gears not learned"), "says what is not ready");
  const profileRequests = [];
  routes["/api/setup/profile"] = (options) => {
    profileRequests.push(JSON.parse(options.body));
    return profileRequests.length === 1 ? { error: "engine size must be a number of litres, such as 2.0" } : DATA.profile;
  };
  $("setup-litres").value = "big";
  await $("setup-save").fire("click");
  check(text($("setup-profile-note")).includes("must be a number of litres"), "explains a refused engine size");
  $("setup-litres").value = "2.0";
  $("setup-transmission").value = "dual-clutch automatic";
  await $("setup-save").fire("click");
  check(profileRequests[1].engine_litres === "2.0" && profileRequests[1].transmission === "dual-clutch automatic", "sends the profile");
  check(text($("setup-summary")).includes("Uses the 2 L you entered"), "the summary follows: " + text($("setup-summary")));

  routes["/api/setup/baseline"] = { error: "the engine is not warm yet (coolant 20 degrees); try again once it is" };
  await $("baseline-start").fire("click");
  check(text($("baseline-note")) === "Keep idling: 60 s to go" && $("baseline-start").disabled === true, "counts the minute down: " + text($("baseline-note")));
  let ticks = 0;
  while (timers.length) {
    timers.shift()();
    ticks++;
  }
  await settle();
  check(ticks === 60, "one tick a second for a minute, got " + ticks);
  check(text($("baseline-note")).startsWith("The engine is not warm yet") && $("baseline-start").disabled === false, "then says why no baseline was kept");
  const kept = { values: { idle_rpm: 780, idle_map: 34, ltft: 12.5 }, seconds: 58, flags: ["long-term fuel trim is beyond ±10 %"], good: false, taken_at: 0 };
  routes["/api/setup/baseline"] = Object.assign({}, DATA.profile, { baseline: kept });
  $("baseline-good").checked = true;
  await $("baseline-start").fire("click");
  while (timers.length) timers.shift()();
  await settle();
  const baselineRequest = JSON.parse(calls.filter((call) => call.path === "/api/setup/baseline").pop().options.body);
  check(baselineRequest.known_good === true, "passes on that the car is said to be running well");
  check(text($("baseline-state")).includes("Kept as the current state, not as known good"), "but a flagged baseline is not called good: " + text($("baseline-state")));
  check(text($("baseline-state")).includes("Long-term fuel trim is beyond ±10 %"), "and says what flagged it");

  routes["/api/setup/gears"] = DATA.gears;
  await $("gears-learn").fire("click");
  check(text($("gears-state")).includes("120") && text($("setup-summary")).includes("6 gears learned"), "learned gears are listed: " + text($("gears-state")));
  routes["/api/setup/gears"] = { error: "no steady gears found there yet; drive gently and hold each gear for a few seconds" };
  await $("gears-learn").fire("click");
  check(text($("gears-note")).startsWith("No steady gears found"), "explains when a drive has no gears in it");
  // Setup: values only this maker has.
  routes["/api/maker"] = DATA.maker;
  await loadMaker();
  check($("maker-steps").hidden === false && $("maker-empty").hidden === true, "offers maker-specific values on a CAN car");
  check($("maker-module").value === "7E9", "starts on the transmission module");
  check(text($("maker-values")).startsWith("None set up yet"), "nothing set up to begin with");
  const tries = $("maker-candidates").children.filter((node) => node.tag === "button");
  check(tries.length === 2 && text(tries[0]) === "Try Clutch A slip (1EBB)", "offers the leads: " + text($("maker-candidates")));
  check(text($("maker-candidates")).includes("not from the maker"), "and says where they came from");
  const makerRequests = [];
  const slipA = Object.assign({ key: "22:7E9:1EBB" }, DATA.maker.candidates[0]);
  routes["/api/maker/values"] = (options) => {
    const values = JSON.parse(options.body).values;
    makerRequests.push(values);
    if (values.some((value) => value.scale === null)) return { error: "the scale must be a number" };
    return Object.assign({}, DATA.maker, { values: values.map((value) => Object.assign({ key: "22:" + value.module + ":" + value.id }, value)), candidates: DATA.maker.candidates.slice(1) });
  };
  await tries[0].fire("click");
  check(makerRequests[0].length === 1 && makerRequests[0][0].id === "1EBB", "adding a lead sends it");
  check(text($("maker-values")).includes("Clutch A slip") && text($("maker-values")).includes("2 bytes, can be negative, times 0.25"), "and lists it with its rule: " + text($("maker-values")));
  $("maker-id").value = "1e12";
  $("maker-name").value = "Gear";
  $("maker-scale").value = "lots";
  await $("maker-add").fire("click");
  check(text($("maker-note")) === "The scale must be a number." && $("maker-name").value === "Gear", "a bad rule is explained and left to correct");
  $("maker-scale").value = "";
  await $("maker-add").fire("click");
  const sentGear = makerRequests[makerRequests.length - 1][1];
  check(sentGear.id === "1E12" && sentGear.module === "7E9" && sentGear.scale === 1 && sentGear.offset === 0 && sentGear.size === 1, "an added value is sent with plain defaults: " + JSON.stringify(sentGear));
  check($("maker-name").value === "" && text($("maker-values")).includes("Gear"), "and the form is cleared");
  const removers = $("maker-values").descendants().filter((node) => node.tag === "button");
  await removers[0].fire("click");
  check(makerRequests[makerRequests.length - 1].length === 1 && !text($("maker-values")).includes("Clutch A slip"), "a value can be removed");

  const scanRequests = [];
  let gearByte = "03";
  routes["/api/maker/scan"] = (options) => {
    const request = JSON.parse(options.body);
    scanRequests.push(request);
    if (request.first === "1E00") return { found: [{ id: "1E12", data: gearByte }], next: "1E40" };
    if (request.first === "1E40") return { found: [], next: "1E80" };
    return { error: "the car took too long to answer" };
  };
  $("scan-count").value = "256";
  await $("scan-start").fire("click");
  check(scanRequests.length === 3 && scanRequests[1].first === "1E40" && scanRequests[0].count === 64 && scanRequests[0].module === "7E9", "scans in runs of 64, each from where the last ended");
  check(text($("scan-note")) === "The car took too long to answer." && text($("scan-start")) === "Scan", "stops and says why when a run fails");
  check(text($("scan-results")).includes("1E12") && text($("scan-results")).includes("03"), "and keeps what it found: " + text($("scan-results")));
  gearByte = "04";
  $("scan-count").value = "64";
  await $("scan-start").fire("click");
  check(text($("scan-note")) === "1 of 64 identifiers answered", "says how many answered: " + text($("scan-note")));
  check(text($("scan-results")).includes("Changed from 03"), "and what moved since the last scan: " + text($("scan-results")));
  await $("scan-results").descendants().find((node) => node.tag === "button").fire("click");
  check($("maker-id").value === "1E12" && $("maker-size").value === "1", "a found identifier can be taken into the form");
  // Setup: a discovery run.
  routes["/api/discoveries"] = DATA.discoveries;
  await loadDiscoveries();
  check(text($("discover-runs")) === "No discovery runs yet." && text($("discover-start")) === "Start a discovery run", "no runs to begin with");
  check($("discover-reuse").children.length === 1 && $("discover-count").value === "256", "offers to ask through a range");
  const discoverRequests = [];
  const scanningNow = { id: 1, module: "7E9", phase: "scanning", asked: 48, range: 1024, found: 2, readings: 2, seconds: 3.1 };
  const finished = { id: 1, started_at: 1700000000, ended_at: 1700000600, vin: "1FADP3F2XHL123456", module: "7E9", note: null, identifiers: 6, readings: 1800, seconds: 598.2 };
  routes["/api/discover"] = (options) => {
    const request = JSON.parse(options.body);
    discoverRequests.push(request);
    if (request.action === "stop") return Object.assign({}, DATA.discoveries, { active: null, runs: [finished] });
    if (request.count === 8192) return { error: "a discovery run is already going; stop it first" };
    return Object.assign({}, DATA.discoveries, { active: scanningNow });
  };
  $("scan-first").value = "1e00";
  $("discover-count").value = "8192";
  await $("discover-start").fire("click");
  check(text($("discover-note")) === "A discovery run is already going; stop it first.", "explains a refused start");
  $("discover-count").value = "1024";
  await $("discover-start").fire("click");
  const begun = discoverRequests[1];
  check(begun.action === "start" && begun.module === "7E9" && begun.first === "1E00" && begun.count === 1024 && begun.reuse === null, "starts a run over the chosen range: " + JSON.stringify(begun));
  check(text($("discover-state")) === "Run 1: asking the module what it has, 48 of 1,024 identifiers, 2 found so far", "says how the scan is going: " + text($("discover-state")));
  check(text($("discover-start")) === "Stop the discovery run", "the button now stops it");
  feed(Object.assign({}, live[0], { status: Object.assign({}, live[0].status, { discovery: Object.assign({}, scanningNow, { phase: "capturing", found: 6, readings: 412, seconds: 95 }) }) }));
  check(text($("discover-state")) === "Run 1: reading 6 identifiers in turn, 412 readings over 1 min 35 s. Drive, then stop the run.", "and then how the capture is going: " + text($("discover-state")));
  routes["/api/discoveries"] = Object.assign({}, DATA.discoveries, { active: null, runs: [finished] });
  await $("discover-start").fire("click");
  await settle();
  check(discoverRequests[2].action === "stop" && text($("discover-state")) === "" && text($("discover-start")) === "Start a discovery run", "stopping ends it");
  check(text($("discover-runs")).includes("7E9") && text($("discover-runs")).includes("9 min 58 s"), "and lists the run: " + text($("discover-runs")));
  check($("discover-reuse").children.length === 2 && text($("discover-reuse").children[1]) === "Read again the 6 identifiers run 1 found", "which a later run can read again without scanning");
  const rawLink = $("discover-runs").descendants().find((node) => node.tag === "a");
  check(rawLink.getAttribute("href") === "/api/discoveries/1.csv", "links to the raw bytes");

  routes["/api/discoveries/1"] = {
    run: { id: 1, module: "7E9", vin: "1FADP3F2XHL123456", note: null, started_at: 1700000000, ended_at: 1700000600, seconds: 598.2 },
    gears_known: false, passes: 2400,
    moving: [
      { id: "1E12", bytes: 1, readings: 300, last: "03", first: "01", score: 0.97,
        readings_of: [{ start: 0, size: 1, signed: false, low: 1, high: 6, distinct: 6, moves_with: [{ what: "the gear", likeness: 0.97 }], gear_match: 0.97, guess: "Equals the gear worked out from the ratio in 97 % of readings: likely the gear in use", score: 0.97 }] },
      { id: "1E30", bytes: 3, readings: 300, last: "800A3C", first: "800000", score: 0.99,
        readings_of: [{ start: 1, size: 2, signed: true, low: -5, high: 2790, distinct: 250, moves_with: [{ what: "engine speed", likeness: 0.93 }, { what: "the speed of the shaft in use", likeness: 0.99 }], gear_match: null, guess: "Follows the speed of the shaft in use more closely than engine speed: likely an input shaft speed", score: 0.99 }] },
    ],
    still: [{ id: "1E01", bytes: 4, readings: 300, last: "44505336", first: "44505336" }],
  };
  await $("discover-runs").descendants().find((node) => node.tag === "button").fire("click");
  const moved = text($("discover-report"));
  for (const expected of ["Run 1: what moved over 9 min 58 s", "Gears have not been learned", "1E12", "byte 1", "the gear 0.97", "likely the gear in use",
    "bytes 2 to 3, can be negative", "80 0A 3C", "1 identifier answered but never changed: 1E01 (44 50 53 36).", "These are leads."]) {
    check(moved.includes(expected), "the report shows " + expected + " in: " + moved);
  }
  const takers = $("discover-report").descendants().filter((node) => node.tag === "button");
  await takers[1].fire("click");
  check($("maker-id").value === "1E30" && $("maker-start").value === "1" && $("maker-size").value === "2" && $("maker-signed").checked === true, "a lead can be taken into the form, with where it starts");
  check(text($("maker-note")).startsWith("Taken from run 1."), "and says what is still needed");
  $("maker-name").value = "Input shaft speed";
  await $("maker-add").fire("click");
  const sentShaft = makerRequests[makerRequests.length - 1].pop();
  check(sentShaft.start === 1 && sentShaft.size === 2 && sentShaft.signed === true, "the value is saved from its second byte: " + JSON.stringify(sentShaft));
  check(text($("maker-values")).includes("skip 1, then 2 bytes, can be negative"), "and its rule says so: " + text($("maker-values")));
  routes["/api/discoveries/1"] = Object.assign({}, routes["/api/discoveries/1"], { gears_known: true, still: [] });
  await $("discover-runs").descendants().find((node) => node.tag === "button").fire("click");
  check(!text($("discover-report")).includes("Gears have not been learned") && !text($("discover-report")).includes("never changed"), "notes that do not apply are left out");
  sane($("discover-report"), "the discovery report");
  routes["/api/discoveries/1"] = { error: "no discovery run 1" };
  await $("discover-runs").descendants().find((node) => node.tag === "button").fire("click");
  check(text($("discover-report")).includes("No discovery run 1"), "a run that has gone is explained");
  showMaker(Object.assign({}, DATA.maker, { supported: false, modules: [], candidates: [] }));
  check($("maker-steps").hidden === true && $("maker-empty").hidden === false, "says so where the network is not one it can read these on");
  sane($("setup-steps"), "setup");
  await $("tab-live").fire("click");
  check($("report-bar").hidden === true, "the report bar goes away with its tabs");

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
