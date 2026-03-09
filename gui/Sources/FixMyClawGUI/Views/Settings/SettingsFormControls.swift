import SwiftUI

// MARK: - Section Header

struct SectionHeader: View {
    let title: String
    let description: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.headline)
            Text(description)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Text Field Row

struct TextFieldRow: View {
    let title: String
    @Binding var text: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(title)
                .frame(width: 150, alignment: .leading)

            TextField(title, text: $text)
                .textFieldStyle(.roundedBorder)
        }
    }
}

// MARK: - Picker Row

struct PickerRow: View {
    let title: String
    @Binding var selection: String
    let options: [String]

    var body: some View {
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
        }
    }
}

// MARK: - Line List Editor

struct LineListEditor: View {
    let title: String
    let description: String
    @Binding var text: String

    var body: some View {
        MultilineTextField(
            title: title,
            description: description,
            text: $text,
            minHeight: 110
        )
    }
}

// MARK: - Command List Editor

struct CommandListEditor: View {
    let title: String
    let description: String
    @Binding var text: String

    var body: some View {
        MultilineTextField(
            title: title,
            description: description,
            text: $text,
            minHeight: 130
        )
    }
}
