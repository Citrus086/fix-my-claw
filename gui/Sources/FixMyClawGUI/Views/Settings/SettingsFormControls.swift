import SwiftUI

enum FormMessageTone {
    case info
    case warning
}

struct FormMessage: View {
    let text: String
    let tone: FormMessageTone

    private var tint: Color {
        switch tone {
        case .info:
            return .secondary
        case .warning:
            return .orange
        }
    }

    private var iconName: String {
        switch tone {
        case .info:
            return "info.circle"
        case .warning:
            return "exclamationmark.triangle"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: iconName)
                .font(.caption)
                .foregroundColor(tint)
                .padding(.top, 1)
            Text(text)
                .font(.caption)
                .foregroundColor(tint)
        }
    }
}

// MARK: - Section Header

struct SectionHeader: View {
    let title: String
    let description: String
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)
                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer(minLength: 12)

            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
    }
}

// MARK: - Text Field Row

struct TextFieldRow: View {
    let title: String
    @Binding var text: String
    var description: String? = nil
    var message: String? = nil
    var messageTone: FormMessageTone = .info

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(title)
                    .frame(width: 150, alignment: .leading)

                TextField(title, text: $text)
                    .textFieldStyle(.roundedBorder)
            }

            if let description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.leading, 162)
            }

            if let message, !message.isEmpty {
                FormMessage(text: message, tone: messageTone)
                    .padding(.leading, 162)
            }
        }
    }
}

// MARK: - Picker Row

struct PickerRow: View {
    let title: String
    @Binding var selection: String
    let options: [String]
    var description: String? = nil
    var message: String? = nil
    var messageTone: FormMessageTone = .info

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 12) {
                Text(title)
                    .frame(width: 150, alignment: .leading)

                Picker(title, selection: $selection) {
                    ForEach(options, id: \.self) { option in
                        Text(option).tag(option)
                    }
                }
                .pickerStyle(.menu)

                Spacer()
            }

            if let description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.leading, 162)
            }

            if let message, !message.isEmpty {
                FormMessage(text: message, tone: messageTone)
                    .padding(.leading, 162)
            }
        }
    }
}

// MARK: - Integer Field

struct IntField: View {
    let title: String
    @Binding var value: Int
    let unit: String
    let range: ClosedRange<Int>

    private static let formatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .none
        return formatter
    }()

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            TextField("", value: $value, formatter: Self.formatter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 120)
                .onChange(of: value) { newValue in
                    value = min(range.upperBound, max(range.lowerBound, newValue))
                }

            Text(unit)
                .foregroundColor(.secondary)
                .frame(width: 50, alignment: .leading)

            Spacer()

            Text("(\(range.lowerBound) - \(range.upperBound))")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Double Field

struct DoubleField: View {
    let title: String
    @Binding var value: Double
    let range: ClosedRange<Double>

    private static let formatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = 3
        return formatter
    }()

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            TextField("", value: $value, formatter: Self.formatter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 120)
                .onChange(of: value) { newValue in
                    value = min(range.upperBound, max(range.lowerBound, newValue))
                }

            Spacer()

            Text(String(format: "(%.2f - %.2f)", range.lowerBound, range.upperBound))
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Multiline Text Field

struct MultilineTextField: View {
    let title: String
    let description: String
    @Binding var text: String
    let minHeight: CGFloat
    var message: String? = nil
    var messageTone: FormMessageTone = .info

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.subheadline)
                .fontWeight(.medium)
            Text(description)
                .font(.caption)
                .foregroundColor(.secondary)
            TextEditor(text: $text)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: minHeight)
                .padding(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.25), lineWidth: 1)
                )

            if let message, !message.isEmpty {
                FormMessage(text: message, tone: messageTone)
            }
        }
    }
}

// MARK: - Line List Editor

struct LineListEditor: View {
    let title: String
    let description: String
    @Binding var text: String
    var message: String? = nil
    var messageTone: FormMessageTone = .info

    var body: some View {
        MultilineTextField(
            title: title,
            description: description,
            text: $text,
            minHeight: 110,
            message: message,
            messageTone: messageTone
        )
    }
}

// MARK: - Command List Editor

struct CommandListEditor: View {
    let title: String
    let description: String
    @Binding var text: String
    var message: String? = nil
    var messageTone: FormMessageTone = .info

    var body: some View {
        MultilineTextField(
            title: title,
            description: description,
            text: $text,
            minHeight: 130,
            message: message,
            messageTone: messageTone
        )
    }
}
