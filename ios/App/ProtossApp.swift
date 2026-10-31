import SwiftUI

// The host app exists so the Messages extension has something to ship inside. The product lives in Messages.
@main
struct ProtossApp: App {
    var body: some Scene {
        WindowGroup {
            VStack(alignment: .leading, spacing: 12) {
                Text("PROTOSS").font(.system(size: 28, weight: .black)).tracking(1)
                Text("Protoss lives in your group chat. Open Messages, start a chat with friends, and pick Protoss from the apps row.")
                Text("Say a trade idea, the Lab tests it on Hyperliquid history, friends back it and stake. Every fill is public.")
                    .foregroundStyle(.secondary)
                Link("app.protoss.trade", destination: URL(string: "https://app.protoss.trade/#/huddle/demo")!)
            }
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}
