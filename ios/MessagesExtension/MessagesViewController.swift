import Messages
import SwiftUI
import UIKit

// Protoss inside Messages. A message bubble is a thesis card; its URL carries the thesis id and the huddle name,
// so whoever taps it lands on the same card: back it, stake it, and the bubble updates for everyone.
//   https://app.protoss.trade/t/<id>?h=<huddle>   (also a normal link with a preview where the extension is not installed)
final class MessagesViewController: MSMessagesAppViewController {
    private let model = Model()
    private var host: UIHostingController<RootView>?

    override func viewDidLoad() {
        super.viewDidLoad()
        model.send = { [weak self] thesis, huddle in self?.insert(thesis: thesis, huddle: huddle) }
        model.expand = { [weak self] in self?.requestPresentationStyle(.expanded) }
        let h = UIHostingController(rootView: RootView(model: model))
        addChild(h)
        h.view.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(h.view)
        NSLayoutConstraint.activate([
            h.view.leadingAnchor.constraint(equalTo: view.leadingAnchor), h.view.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            h.view.topAnchor.constraint(equalTo: view.topAnchor), h.view.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        h.didMove(toParent: self)
        host = h
    }

    override func willBecomeActive(with conversation: MSConversation) {
        model.me = conversation.localParticipantIdentifier.uuidString
        load(conversation.selectedMessage)
    }

    override func didSelect(_ message: MSMessage, conversation: MSConversation) {
        load(message)
    }

    override func didTransition(to presentationStyle: MSMessagesAppPresentationStyle) {
        model.expanded = presentationStyle == .expanded
    }

    private func load(_ message: MSMessage?) {
        if let url = message?.url, let c = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            model.huddleName = c.queryItems?.first(where: { $0.name == "h" })?.value ?? model.huddleName
            model.selected = Int(url.pathComponents.last ?? "")
        } else {
            model.selected = nil
        }
        Task { await model.refresh() }
    }

    private func insert(thesis: ProtossAPI.Thesis, huddle: String) {
        guard let conversation = activeConversation else { return }
        Task { @MainActor in
            let layout = MSMessageTemplateLayout()
            layout.caption = "Thesis \(thesis.n) from \(thesis.author): \(thesis.label)"
            layout.subcaption = thesis.testLine
            layout.trailingSubcaption = thesis.backingLine
            if let data = await ProtossAPI.cardImage(thesis: thesis.id) { layout.image = UIImage(data: data) }
            let message = MSMessage(session: conversation.selectedMessage?.session ?? MSSession())
            var c = URLComponents(url: ProtossAPI.base.appendingPathComponent("t/\(thesis.id)"), resolvingAgainstBaseURL: false)!
            c.queryItems = [URLQueryItem(name: "h", value: huddle)]
            message.url = c.url
            message.layout = layout
            message.summaryText = "\(thesis.label): \(thesis.backingLine)"
            try? await conversation.insert(message)
            dismiss()
        }
    }
}

@MainActor
final class Model: ObservableObject {
    @Published var huddle: ProtossAPI.Huddle?
    @Published var selected: Int?
    @Published var expanded = false
    @Published var busy = false
    @Published var error: String?
    @Published var name: String = ""
    var me = "" { didSet { name = Model.names[me] ?? "" } }
    var huddleName: String = UserDefaults.standard.string(forKey: "protoss.huddle") ?? "imsg-\(UUID().uuidString.prefix(6).lowercased())" {
        didSet { UserDefaults.standard.set(huddleName, forKey: "protoss.huddle") }
    }
    var send: ((ProtossAPI.Thesis, String) -> Void)?
    var expand: (() -> Void)?

    // Simulator Messages switches between two people in one install, so names are kept per participant id
    static var names: [String: String] {
        get { UserDefaults.standard.dictionary(forKey: "protoss.names") as? [String: String] ?? [:] }
        set { UserDefaults.standard.set(newValue, forKey: "protoss.names") }
    }

    func setName(_ n: String) {
        name = n.trimmingCharacters(in: .whitespaces)
        var all = Model.names
        all[me] = name
        Model.names = all
    }

    var thesis: ProtossAPI.Thesis? { huddle?.theses.first { $0.id == selected } }

    func refresh() async {
        do { huddle = try await ProtossAPI.huddle(huddleName); error = nil } catch { self.error = "Could not reach Protoss." }
    }

    func propose(_ text: String) async {
        guard let h = huddle, !text.isEmpty else { return }
        busy = true
        defer { busy = false }
        let before = Set(h.theses.map(\.id))
        try? await ProtossAPI.post(huddle: h.id, sender: name, text: text)
        await refresh()
        if let t = huddle?.theses.last(where: { !before.contains($0.id) }) {
            send?(t, huddleName)
        } else {
            let reply = huddle?.messages.last(where: { $0.from_bot })?.text
            error = reply ?? "That did not read as a trade idea. Try: buy XMR every time a major company gets hacked."
        }
    }

    func back(_ t: ProtossAPI.Thesis, stake: Int?) async {
        guard let h = huddle else { return }
        busy = true
        defer { busy = false }
        let card = h.messages.last { $0.kind == "card" && $0.thesis_id == t.id }
        try? await ProtossAPI.post(huddle: h.id, sender: name, reaction: "like", target: card?.guid)
        if let stake { try? await ProtossAPI.post(huddle: h.id, sender: name, text: "in for \(stake)") }
        await refresh()
        if let updated = huddle?.theses.first(where: { $0.id == t.id }) { send?(updated, huddleName) }
    }
}
