using System;
using System.Reflection;
using System.ServiceModel.Channels;
using System.Web;
public sealed class App { public object Dynamic() => Assembly.Load("Plugin"); public Binding Binding() => new CustomBinding(); public HttpContext Context => HttpContext.Current; }
