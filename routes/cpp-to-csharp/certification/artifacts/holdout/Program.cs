var actual0 = Migrated.elmos_fn_bde6d03dcfad148a(20, 10);
if (actual0 != 10) throw new Exception("case 0");
Console.WriteLine("ELMOS_OBSERVATION\t0\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual0, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
var actual1 = Migrated.elmos_fn_bde6d03dcfad148a(-2, 10);
if (actual1 != 0) throw new Exception("case 1");
Console.WriteLine("ELMOS_OBSERVATION\t1\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual1, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
var actual2 = Migrated.elmos_fn_bde6d03dcfad148a(7, 10);
if (actual2 != 7) throw new Exception("case 2");
Console.WriteLine("ELMOS_OBSERVATION\t2\tb64\t" + Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(Convert.ToString(actual2, System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));
