# Protoss in Messages (iMessage extension)

A Messages app extension: a bubble in the group thread is a thesis card (backtest, who backed it, how much is in).
Tap it to back it and pick a stake; the bubble updates in place. It talks to the same engine as the web group
chat and the Mac bridge (`backend/app/huddle.py`, web huddles, paper mode), at `https://app.protoss.trade`.

## Build (Mac mini, headless)
```
brew install xcodegen                    # once
cd ~/protoss/ios && xcodegen             # writes Protoss.xcodeproj and both Info.plists from project.yml (all gitignored)
xcodebuild -project Protoss.xcodeproj -scheme Protoss -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```
## Run in the Simulator's Messages
```
xcrun simctl boot "iPhone 16" 2>/dev/null; open -a Simulator
xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/Protoss.app
```
Open Messages in the Simulator, open the conversation, tap the apps row, pick Protoss. Or from Xcode: scheme
ProtossMessages, Run, choose Messages. Xcode's Messages session has two sides (Kate Bell, John Appleseed); switch
sides to play two friends: one says the idea, the other backs it with $50.

## Real phones
Needs a paid Apple Developer team in `project.yml` (`DEVELOPMENT_TEAM`), then TestFlight for friends. App Store review
only for public release.
