var actual0 = Pricing.calculate(100, 20);
if (actual0 != 120) throw new Exception("case 0");
Console.WriteLine("ELMOS_OBSERVATION\t0\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual0, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
var actual1 = Pricing.calculate(-1, 5);
if (actual1 != 0) throw new Exception("case 1");
Console.WriteLine("ELMOS_OBSERVATION\t1\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual1, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
var actual2 = Pricing.calculate(7, -2);
if (actual2 != 5) throw new Exception("case 2");
Console.WriteLine("ELMOS_OBSERVATION\t2\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual2, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
