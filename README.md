# THIS REPOSITORY IS DEPRECATED #

* Please use the [Qumulo Cloud Q Quick Start](https://aws.amazon.com/quickstart/architecture/qumulo-cloud-q/) for all new deployments.
* This repo will be left as is for previous deployments that reference it.

<!--
# aws-sa-waf-cluster
AWS CloudFormation templates to deploy a Qumulo cluster with one to 20 instances per the AWS Well Architected Framework.
Supports usable capacities from 1TB to 6PB with all Qumulo Core features.

## Requirements

These templates deploy Qumulo AMIs with [Qumulo Core Cloud Software](https://qumulo.com/product/cloud-products/) version `>= 4.0.6`

A subscription to an [AWS Marketplace](https://aws.amazon.com/marketplace/search/results?x=0&y=0&searchTerms=qumulo) offer is required.
For private offers via the AWS Marketplace contact [Qumulo Sales](http://discover.qumulo.com/cloud-calc-contact.html).

## Usage

**IMPORTANT:** The `master` branch is used in `source` just as an example. In your code, do not pin to `master` because there may be breaking changes between releases.
Instead pin to a release tag (e.g. `?ref=tags/vx.y`).

For architectural details, resource requirements, deployment instructions, and configuration options see the [deployment guide](./docs/aws-sa-waf-cluster.pdf).

Reference Architecture:
![Ref Arch](./docs/aws-sa-waf-cluster.png)
-->

## Help

To post feedback, submit feature ideas, or report bugs, use the [Issues](https://github.com/Qumulo/terraform-aws-qumulo-cluster//issues) section of this GitHub repo.

__Note:__ This project is provided as a public service to the AWS/CloudFormation
community and is not directly supported by Qumulo's paid enterprise support. It is
intended to be used by expert users only.

## Copyright

Copyright © 2021 [Qumulo, Inc.](https://qumulo.com)

## License

[![License](https://img.shields.io/badge/license-MIT-green)](https://opensource.org/licenses/MIT)

See [LICENSE](LICENSE) for full details

    MIT License
    
    Copyright (c) 2021 Qumulo, Inc.
    
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

## Trademarks

All other trademarks referenced herein are the property of their respective owners.

### Contributors

 - [dackbusch](https://github.com/dackbusch)
