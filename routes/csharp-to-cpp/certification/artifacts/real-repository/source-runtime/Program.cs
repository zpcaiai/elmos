var actual0 = Difference.difference(20, 7);
if (actual0 != 13) throw new Exception("case 0");
Console.WriteLine("ELMOS_OBSERVATION\t0\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual0, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
var actual1 = Difference.difference(3, 8);
if (actual1 != 0) throw new Exception("case 1");
Console.WriteLine("ELMOS_OBSERVATION\t1\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual1, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
var actual2 = Difference.difference(4, 4);
if (actual2 != 0) throw new Exception("case 2");
Console.WriteLine("ELMOS_OBSERVATION\t2\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual2, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
