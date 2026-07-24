using System.Drawing;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace EasiAuto.Core.Converters;

/// <summary>
/// 将 <see cref="Point"/> 序列化为 JSON 数组 [X, Y]，
/// 并从 JSON 数组反序列化回 <see cref="Point"/>。
/// </summary>
public class PointJsonConverter : JsonConverter<Point>
{
    public override Point Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.StartArray)
            throw new JsonException("Point 类型的 JSON 值必须是数组格式 [X, Y]");

        var values = new List<int>(2);

        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.EndArray)
                break;

            if (reader.TokenType == JsonTokenType.Number)
                values.Add(reader.GetInt32());
        }

        if (values.Count < 2)
            throw new JsonException($"Point 数组至少需要 2 个元素，实际只有 {values.Count} 个");

        return new Point(values[0], values[1]);
    }

    public override void Write(Utf8JsonWriter writer, Point value, JsonSerializerOptions options)
    {
        writer.WriteStartArray();
        writer.WriteNumberValue(value.X);
        writer.WriteNumberValue(value.Y);
        writer.WriteEndArray();
    }
}
