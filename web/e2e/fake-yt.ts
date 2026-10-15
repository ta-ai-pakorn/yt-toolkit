import { expect, type Page, type Request } from "@playwright/test"

/**
 * YouTube IFrame API ปลอมสำหรับ e2e (M3.5): เทสต์ไม่ต่อยูทูปจริง
 *
 * - ดัก https://www.youtube.com/iframe_api แล้วส่งสคริปต์ปลอมที่สร้าง window.YT.Player
 * - ดัก iframe ของ youtube.com / youtube-nocookie.com/embed/ ให้เป็นหน้าเปล่า
 * - ตัวเล่นปลอมนับเวลาเองระหว่าง "เล่น" (rate เร่งเวลาได้) และบันทึก seek/state ไว้ใน window.__fakeYT
 * - เล่นถึง durationS = ENDED (เหมือนของจริง) · playVideo ขณะเล่นอยู่แล้วไม่ยิง PLAYING ซ้ำ (เหมือนของจริง)
 * - จำลองพฤติกรรมของจริงที่ทำให้แอพพังได้: staleAfterSeekMs (เวลาเก่าค้างหลัง seek), autoplayBlocked (เบราว์เซอร์ไม่ให้เล่นเอง)
 * - รับได้ทั้ง element ธรรมดา (สร้าง iframe แทนที่) และ iframe ที่สร้างไว้แล้ว (ใช้ iframe นั้น)
 */

export type FakeYTOptions = {
  /** โหลดสคริปต์ไม่ได้ (จำลองออฟไลน์) */
  failScript?: boolean
  /** playVideo() แล้วยิง onError ด้วยรหัสนี้ เช่น 150 = เจ้าของไม่ให้ฝัง */
  errorCode?: number
  /** ความเร็วเวลา (1 = เวลาจริง) */
  rate?: number
  /** ความยาวคลิปเป็นวินาที (เล่นถึงแล้ว ENDED) */
  durationS?: number
  /**
   * หลัง seek getCurrentTime ยังคืนเวลาเก่าอยู่เท่านี้ ms (ของจริงเป็นแบบนี้ตอนเน็ตช้า/บัฟเฟอร์)
   * ระหว่างนั้น playVideo จากสถานะไม่เล่น = BUFFERING ก่อน แล้วค่อย PLAYING เมื่อพ้นช่วงนี้
   */
  staleAfterSeekMs?: number
  /** เบราว์เซอร์ไม่ให้เล่นเอง: playVideo ครั้งแรก (ตอนพร้อม) ไม่เล่น สถานะค้าง UNSTARTED จนมีการกดเล่นครั้งที่สอง */
  autoplayBlocked?: boolean
}

const FAKE_SCRIPT = String.raw`(function () {
  var S = { UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5 };
  var cfg = window.__fakeYTConfig || {};
  var log = (window.__fakeYT = window.__fakeYT || { players: [], seeks: [], states: [], calls: [] });
  function Player(el, opts) {
    var node = typeof el === "string" ? document.getElementById(el) : el;
    this.opts = opts || {};
    this.base = 0;
    this.since = 0;
    this.state = S.UNSTARTED;
    this.staleUntil = 0;
    this.staleValue = 0;
    this.plays = 0;
    this.readsSinceSeek = 0;
    if (node.tagName !== "IFRAME") {
      var f = document.createElement("iframe");
      f.src = (this.opts.host || "https://www.youtube.com") + "/embed/" + (this.opts.videoId || "");
      node.replaceWith(f);
      node = f;
    }
    this.iframe = node;
    log.players.push(this);
    var self = this;
    setTimeout(function () { self.emit("onReady", { target: self }); }, 30);
  }
  Player.prototype.emit = function (name, data) {
    var h = this.opts.events && this.opts.events[name];
    if (h) h(data);
  };
  Player.prototype.duration = function () { return cfg.durationS || 600; };
  Player.prototype.now = function () {
    var rate = cfg.rate || 1;
    var t = this.state === S.PLAYING ? this.base + ((performance.now() - this.since) / 1000) * rate : this.base;
    return Math.min(t, this.duration());
  };
  /** เล่นถึงท้ายคลิป = ENDED (ยิงหลังคืนค่าเวลา ไม่ยิงกลางคำสั่งที่ adapter เรียกอยู่) */
  Player.prototype.checkEnded = function () {
    var self = this;
    if (self.state !== S.PLAYING || self.endPending || self.now() < self.duration()) return;
    self.endPending = true;
    setTimeout(function () {
      self.endPending = false;
      if (self.state !== S.PLAYING) return;
      self.base = self.duration();
      self.setState(S.ENDED);
    }, 0);
  };
  Player.prototype.setState = function (s) {
    this.state = s;
    log.states.push(s);
    this.emit("onStateChange", { data: s, target: this });
  };
  Player.prototype.playVideo = function () {
    log.calls.push("play");
    if (cfg.errorCode != null) { this.emit("onError", { data: cfg.errorCode, target: this }); return; }
    this.plays += 1;
    if (cfg.autoplayBlocked && this.plays === 1) { log.calls.push("play-blocked"); return; }
    // เล่นอยู่แล้ว: ของจริงไม่ยิง PLAYING ซ้ำ
    if (this.state === S.PLAYING) return;
    if (this.state === S.ENDED) this.base = 0;
    var self = this;
    var wait = this.staleUntil - performance.now();
    if (wait > 0) {
      // ยังบัฟเฟอร์ตำแหน่งใหม่อยู่: BUFFERING ก่อน แล้ว PLAYING เมื่อพร้อม
      this.setState(S.BUFFERING);
      setTimeout(function () {
        if (self.state !== S.BUFFERING) return;
        self.since = performance.now();
        self.setState(S.PLAYING);
      }, wait);
      return;
    }
    this.base = this.now(); this.since = performance.now();
    this.setState(S.PLAYING);
  };
  Player.prototype.pauseVideo = function () {
    log.calls.push("pause");
    this.base = this.now();
    this.setState(S.PAUSED);
  };
  Player.prototype.stopVideo = function () {
    log.calls.push("stop");
    this.base = 0;
    this.setState(S.CUED);
  };
  Player.prototype.seekTo = function (sec) {
    log.calls.push("seek");
    log.seeks.push(sec);
    this.readsSinceSeek = 0;
    if (cfg.staleAfterSeekMs) {
      this.staleValue = this.now();
      this.staleUntil = performance.now() + cfg.staleAfterSeekMs;
    }
    this.base = Math.min(sec, this.duration()); this.since = performance.now();
  };
  Player.prototype.getCurrentTime = function () {
    if (performance.now() < this.staleUntil) return this.staleValue;
    this.readsSinceSeek += 1;
    this.checkEnded();
    return this.now();
  };
  /** เวลาเล่นเดินไปถึง sec เอง (ไม่ใช่ seek: ไม่บันทึกใน seeks) ใช้กับ playTo() ในเทสต์ */
  Player.prototype.playTo = function (sec) {
    this.base = Math.min(sec, this.duration()); this.since = performance.now();
  };
  Player.prototype.getDuration = function () { return this.duration(); };
  Player.prototype.getPlaybackRate = function () { return cfg.rate || 1; };
  Player.prototype.getPlayerState = function () { return this.state; };
  Player.prototype.getIframe = function () { return this.iframe; };
  Player.prototype.destroy = function () { log.calls.push("destroy"); this.iframe.remove(); };
  window.YT = { Player: Player, PlayerState: S, loaded: 1 };
  setTimeout(function () { if (typeof window.onYouTubeIframeAPIReady === "function") window.onYouTubeIframeAPIReady(); }, 0);
})();`

const isYouTube = (url: string) => /^https:\/\/([a-z0-9-]+\.)*(youtube\.com|youtube-nocookie\.com|ytimg\.com|googlevideo\.com)\//.test(url)

/**
 * ติดตั้งก่อน page.goto คืนรายการคำขอไปยูทูปทั้งหมด (ใช้ตรวจว่าไม่มีคำขอก่อนกดเล่น)
 * setFailScript (เพิ่มโดย lane P): เปลี่ยนว่าโหลดสคริปต์ได้หรือไม่ระหว่างเทสต์ เช่นออฟไลน์แล้วกด "ลองอีกครั้ง"
 */
export async function installFakeYT(
  page: Page,
  options: FakeYTOptions = {},
): Promise<{ requests: string[]; setFailScript: (fail: boolean) => void }> {
  const requests: string[] = []
  let failScript = options.failScript === true
  page.on("request", (req: Request) => {
    if (isYouTube(req.url()) && !req.url().includes("i.ytimg.com")) requests.push(req.url())
  })
  await page.addInitScript((cfg) => {
    ;(window as unknown as { __fakeYTConfig: unknown }).__fakeYTConfig = cfg
  }, options)
  await page.route("https://www.youtube.com/iframe_api", (route) =>
    failScript
      ? route.abort("internetdisconnected")
      : route.fulfill({ contentType: "text/javascript", body: FAKE_SCRIPT }),
  )
  await page.route(/^https:\/\/www\.(youtube|youtube-nocookie)\.com\/embed\//, (route) =>
    route.fulfill({ contentType: "text/html", body: "<!doctype html><html><body style='margin:0;background:#000'></body></html>" }),
  )
  return {
    requests,
    setFailScript: (fail: boolean) => {
      failScript = fail
    },
  }
}

/** บันทึกของตัวเล่นปลอม: seek (วินาที), state และชื่อคำสั่งที่ถูกเรียก */
export async function fakeYTLog(page: Page): Promise<{ seeks: number[]; states: number[]; calls: string[]; players: number }> {
  return page.evaluate(() => {
    const log = (window as unknown as { __fakeYT?: { seeks: number[]; states: number[]; calls: string[]; players: unknown[] } }).__fakeYT
    return log
      ? { seeks: [...log.seeks], states: [...log.states], calls: [...log.calls], players: log.players.length }
      : { seeks: [], states: [], calls: [], players: 0 }
  })
}

type FakePlayerHandle = { readsSinceSeek: number; playTo(seconds: number): void }

/**
 * ให้ตัวเล่นปลอมตัวล่าสุด "เล่นถึง" เวลานี้ (วินาที) เหมือนเวลาเดินไปเอง ไม่นับเป็น seek
 * ใช้คู่กับ rate ต่ำมาก (นาฬิกาแทบหยุด): แต่ละสถานะของแอพค้างอยู่จนเทสต์ตรวจเสร็จ ไม่ต้องแข่งกับเวลาที่เร่งไว้
 * รอให้แอพอ่านเวลาหลัง seek ล่าสุดก่อน: adapter ทิ้งเวลาที่ห่างจากจุด seek เกินค่าที่ยอมรับ จนกว่าจะเห็นว่า seek ถึงแล้ว
 * (การอ่านครั้งนั้นกับการยืนยัน seek เกิดใน tick เดียวกัน อ่านแล้ว = adapter รับเวลาถัดไปแน่นอน)
 */
export async function playTo(page: Page, seconds: number): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(() => {
        const players = (window as unknown as { __fakeYT: { players: FakePlayerHandle[] } }).__fakeYT.players
        return (players.at(-1)?.readsSinceSeek ?? 0) > 0
      }),
    )
    .toBe(true)
  await page.evaluate((value) => {
    const players = (window as unknown as { __fakeYT: { players: FakePlayerHandle[] } }).__fakeYT.players
    players.at(-1)?.playTo(value)
  }, seconds)
}
