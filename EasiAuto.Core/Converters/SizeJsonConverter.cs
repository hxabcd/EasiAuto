using System.Drawing;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace EasiAuto.Core.Converters;

/// <summary>
/// 将 <see cref="Size"/> 序列化为 JSON 数组 [Width, Height]，
/// 并从 JSON 数组反序列化回 <see cref="Size"/>。
/// </summary>
public class SizeJsonConverter : JsonConverter<Size>
{
    public override Size Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.StartArray)
            throw new JsonException("Size 类型的 JSON 值必须是数组格式 [Width, Height]");

        var values = new List<int>(2);

        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.EndArray)
                break;

            if (reader.TokenType == JsonTokenType.Number)
                values.Add(reader.GetInt32());
        }

        if (values.Count < 2)
            throw new JsonException($"Size 数组至少需要 2 个元素，实际只有 {values.Count} 个");

        return new Size(values[0], values[1]);
    }

    public override void Write(Utf8JsonWriter writer, Size value, JsonSerializerOptions options)
    {
        writer.WriteStartArray();
        writer.WriteNumberValue(value.Width);
        writer.WriteNumberValue(value.Height);
        writer.WriteEndArray();
    }
}
