import SwiftUI

// Ink and paper, one red rule under the live state: brain/design.md.
private let red = Color(red: 0.784, green: 0.063, blue: 0.180)
private let examples = [
    "let's buy XMR every time a major company gets hacked",
    "what if we bought BTC every Monday and sold Friday",
    "I think the Knicks win game 3 now that Brunson is back",
]

struct RootView: View {
    @ObservedObject var model: Model
    var body: some View {
        Group {
            if model.name.isEmpty { NameView(model: model) }
            else if let t = model.thesis { CardView(model: model, t: t) }
            else { ComposeView(model: model) }
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct NameView: View {
    @ObservedObject var model: Model
    @State private var text = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What do your friends call you?").font(.headline)
            HStack {
                TextField("first name", text: $text).textFieldStyle(.roundedBorder).onTapGesture { model.expand?() }
                Button("Save") { model.setName(text) }.buttonStyle(.borderedProminent).tint(.primary).disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }
}

struct ComposeView: View {
    @ObservedObject var model: Model
    @State private var text = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Say a trade idea").font(.headline)
            HStack {
                TextField("buy XMR every time…", text: $text).textFieldStyle(.roundedBorder).onTapGesture { model.expand?() }
                Button(model.busy ? "Testing" : "Test it") { Task { await model.propose(text) } }
                    .buttonStyle(.borderedProminent).tint(.primary).disabled(model.busy || text.isEmpty)
            }
            if let e = model.error { Text(e).font(.footnote).foregroundStyle(.secondary) }
            if model.expanded {
                ForEach(examples, id: \.self) { e in
                    Button(e) { text = e }.font(.footnote).buttonStyle(.bordered).tint(.secondary)
                }
                Text("The Lab tests it on Hyperliquid history and drops a card here. Friends back it and stake; paper money for now.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
    }
}

struct CardView: View {
    @ObservedObject var model: Model
    let t: ProtossAPI.Thesis
    @State private var stake = 50
    var mine: Bool { t.backers.contains { $0.who == model.name && $0.approved } }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Thesis \(t.n) from \(t.author)").font(.footnote).foregroundStyle(.secondary)
            Text(t.label.uppercased()).font(.system(size: 22, weight: .black)).lineLimit(3)
            Text(t.testLine).font(.system(.footnote, design: .monospaced))
            Text(t.backingLine).font(.subheadline)
            if t.record.closed > 0 {
                Text(String(format: "Record: %d of %d up, %@$%.2f", t.record.up, t.record.closed, t.record.pnl_usd >= 0 ? "+" : "-", abs(t.record.pnl_usd)))
                    .font(.system(.footnote, design: .monospaced))
            }
            if t.status == "live" { Rectangle().fill(red).frame(height: 2) }
            if t.status == "proposed" || (t.status == "live" && t.kind == "rule" && !mine) {
                if t.kind == "rule" {
                    Picker("Stake", selection: $stake) { ForEach([25, 50, 100], id: \.self) { Text("$\($0)").tag($0) } }.pickerStyle(.segmented)
                }
                Button(mine ? "Update" : (t.kind == "rule" ? "Back it with $\(stake)" : "Back it")) {
                    Task { await model.back(t, stake: t.kind == "rule" ? stake : nil) }
                }
                .buttonStyle(.borderedProminent).tint(.primary).disabled(model.busy)
            }
            Text("Paper money. Every fill is public at app.protoss.trade.").font(.caption2).foregroundStyle(.secondary)
        }
    }
}
