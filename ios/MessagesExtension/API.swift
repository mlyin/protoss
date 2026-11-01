import Foundation

// The same group-chat engine the web view and the Mac bridge use (backend/app/huddle.py).
// Web huddles ("web:<name>") are open in paper mode, so the extension needs no key.
enum ProtossAPI {
    static var base = URL(string: UserDefaults.standard.string(forKey: "protoss.api") ?? "https://app.protoss.trade")!

    struct Huddle: Decodable { let id: Int; let title: String; let quorum: Int; let messages: [Message]; let theses: [Thesis] }
    struct Message: Decodable { let id: Int; let guid: String?; let sender: String; let text: String; let from_bot: Bool; let kind: String; let thesis_id: Int? }
    struct Backer: Decodable { let who: String; let approved: Bool; let pledge_usd: Double? }
    struct Record: Decodable { let closed: Int; let up: Int; let pnl_usd: Double }
    struct Events: Decodable { let events: Int; let event_mean_pct: Double?; let any_mean_pct: Double?; let event_up: Int? }
    struct Test: Decodable { let market: String?; let return_pct: Double?; let max_drawdown_pct: Double?; let hold_days: Int?; let real: Bool?; let events: Events? }
    struct Thesis: Decodable, Identifiable {
        let id: Int; let n: Int; let author: String; let label: String; let kind: String; let status: String
        let outcome: String?; let pledged_usd: Double; let backers: [Backer]; let record: Record; let test: Test?
    }

    static func huddle(_ name: String) async throws -> Huddle {
        let (data, _) = try await URLSession.shared.data(from: base.appendingPathComponent("huddle/web/\(name)"))
        return try JSONDecoder().decode(Huddle.self, from: data)
    }

    static func post(huddle id: Int, sender: String, text: String = "", reaction: String? = nil, target: String? = nil) async throws {
        var req = URLRequest(url: base.appendingPathComponent("huddle/\(id)/messages"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "content-type")
        var body: [String: Any] = ["sender": sender, "text": text]
        if let reaction { body["reaction"] = reaction }
        if let target { body["target_guid"] = target }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        _ = try await URLSession.shared.data(for: req)
    }

    static func cardImage(thesis id: Int) async -> Data? {
        try? await URLSession.shared.data(from: base.appendingPathComponent("og/t/\(id).png")).0
    }
}

extension ProtossAPI.Thesis {
    var testLine: String {
        if kind == "call" { return outcome.map { "Call: \($0)" } ?? "A call, scored when it resolves" }
        guard let t = test else { return "" }
        if let e = t.events, e.events > 0, let a = e.event_mean_pct, let b = e.any_mean_pct {
            return String(format: "%@ %+.1f%% after an event vs %+.1f%% any day, %d of %d up", t.market ?? "", a, b, e.event_up ?? 0, e.events)
        }
        return String(format: "Backtest %+.1f%%, max drawdown %.1f%%", t.return_pct ?? 0, t.max_drawdown_pct ?? 0)
    }
    var backingLine: String {
        let on = backers.filter(\.approved)
        if on.isEmpty { return "Needs backing" }
        let who = on.map { b in b.pledge_usd.map { "\(b.who) $\(Int($0))" } ?? b.who }.joined(separator: ", ")
        let state = status == "live" ? "Live" : "Backed"
        return pledged_usd > 0 ? "\(state): \(who), $\(Int(pledged_usd)) in" : "\(state): \(who)"
    }
}
